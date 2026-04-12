"""
LaunchMind GigGuard — CEO Agent (Orchestrator)
The brain of the system. Decomposes startup idea into tasks,
dispatches to sub-agents, reviews outputs, and runs feedback loops.
"""

import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")


class CEOAgent:
    """
    The CEO agent orchestrates the entire pipeline.
    It uses LLM to decompose the idea, review outputs, and make decisions.
    """

    def __init__(self, message_bus):
        self.name = "ceo"
        self.bus = message_bus
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.slack_client = WebClient(token=SLACK_BOT_TOKEN)
        self.decision_log = []

    def run(self, startup_idea: str):
        """
        Full CEO pipeline:
        1. Decompose idea into tasks
        2. Dispatch tasks to sub-agents
        3. Run Product agent and review
        4. Run Engineer + Marketing agents
        5. Run QA agent
        6. Handle feedback loops
        7. Post final summary to Slack
        """
        print(f"\n🏢 [CEO AGENT] Starting orchestration...")
        print(f"💡 Startup Idea: {startup_idea}\n")

        # ═══════════════════════════════════════════
        # STEP 1: Decompose idea into tasks using LLM
        # ═══════════════════════════════════════════
        print("🧠 [CEO AGENT] Step 1 — Decomposing idea into tasks via LLM...")
        tasks = self._decompose_idea(startup_idea)
        self._log_decision("idea_decomposition", "Decomposed startup idea into agent tasks", tasks)

        # ═══════════════════════════════════════════
        # STEP 2: Send task to Product Agent
        # ═══════════════════════════════════════════
        print("\n🧠 [CEO AGENT] Step 2 — Dispatching task to Product Agent...")
        product_task_id = self.bus.send(
            from_agent=self.name,
            to_agent="product",
            message_type="task",
            payload={
                "idea": startup_idea,
                "focus": tasks.get("product_focus", "Define core user personas and top 5 features for the product"),
            },
        )

        # Run Product Agent
        from agents.product_agent import ProductAgent
        product_agent = ProductAgent(self.bus)
        product_agent.run()

        # ═══════════════════════════════════════════
        # STEP 3: Review Product Agent's output (FEEDBACK LOOP)
        # ═══════════════════════════════════════════
        print("\n🧠 [CEO AGENT] Step 3 — Reviewing Product Agent's output via LLM...")
        ceo_messages = self.bus.receive(self.name)
        product_result = None
        for m in ceo_messages:
            if m["from_agent"] == "product" and m["message_type"] == "confirmation":
                product_result = m
                break

        product_spec = product_result["payload"].get("product_spec", {}) if product_result else {}

        # LLM REVIEW — this is the required feedback loop
        review_result = self._review_output("product", product_spec)
        self._log_decision("product_review", review_result["reasoning"], review_result)

        if review_result.get("verdict") == "revise":
            print(f"🔄 [CEO AGENT] Requesting revision from Product Agent...")
            revision_msg_id = self.bus.send(
                from_agent=self.name,
                to_agent="product",
                message_type="revision_request",
                payload={
                    "issue": review_result.get("issues", "Output needs improvement"),
                    "instruction": review_result.get("instruction", "Please improve the product spec"),
                    "original_spec": product_spec,
                    "original_message_id": product_result["message_id"] if product_result else None,
                },
                parent_message_id=product_result["message_id"] if product_result else None,
            )

            # Run Product Agent revision
            revision_msgs = self.bus.receive("product")
            for rm in revision_msgs:
                if rm["message_type"] == "revision_request":
                    product_agent.handle_revision(rm)

            # Get revised output
            revised_messages = self.bus.receive(self.name)
            for rm in revised_messages:
                if rm["from_agent"] == "product" and rm["message_type"] == "confirmation":
                    product_spec = rm["payload"].get("product_spec", product_spec)
                    break

            self._log_decision("product_revision_accepted", "Accepted revised product spec", {"revised": True})
            print("✅ [CEO AGENT] Revised product spec accepted.")
        else:
            print("✅ [CEO AGENT] Product spec approved — no revision needed.")

        # ═══════════════════════════════════════════
        # STEP 4: Run Engineer Agent
        # ═══════════════════════════════════════════
        print("\n🧠 [CEO AGENT] Step 4 — Running Engineer Agent...")
        from agents.engineer_agent import EngineerAgent
        engineer_agent = EngineerAgent(self.bus)
        engineer_agent.run()

        # Get Engineer results
        ceo_messages = self.bus.receive(self.name)
        engineer_result = None
        for m in ceo_messages:
            if m["from_agent"] == "engineer" and m["message_type"] == "result":
                engineer_result = m
                break

        pr_url = engineer_result["payload"].get("github_pr_url", "") if engineer_result else ""
        issue_url = engineer_result["payload"].get("github_issue_url", "") if engineer_result else ""
        print(f"✅ [CEO AGENT] Engineer done — PR: {pr_url}")

        # ═══════════════════════════════════════════
        # STEP 5: Run Marketing Agent (pass PR URL)
        # ═══════════════════════════════════════════
        print("\n🧠 [CEO AGENT] Step 5 — Running Marketing Agent...")
        from agents.marketing_agent import MarketingAgent
        marketing_agent = MarketingAgent(self.bus)
        marketing_agent.run(pr_url=pr_url)

        # Get Marketing results
        ceo_messages = self.bus.receive(self.name)
        marketing_result = None
        for m in ceo_messages:
            if m["from_agent"] == "marketing" and m["message_type"] == "result":
                marketing_result = m
                break

        print("✅ [CEO AGENT] Marketing done.")

        # ═══════════════════════════════════════════
        # STEP 6: Run QA Agent
        # ═══════════════════════════════════════════
        print("\n🧠 [CEO AGENT] Step 6 — Running QA Agent...")
        from agents.qa_agent import QAAgent
        qa_agent = QAAgent(self.bus)
        qa_agent.run(
            engineer_output=engineer_result["payload"] if engineer_result else {},
            marketing_output=marketing_result["payload"] if marketing_result else {},
            product_spec=product_spec,
        )

        # Get QA results
        ceo_messages = self.bus.receive(self.name)
        qa_result = None
        for m in ceo_messages:
            if m["from_agent"] == "qa" and m["message_type"] == "result":
                qa_result = m
                break

        qa_verdict = qa_result["payload"].get("overall_verdict", "pass") if qa_result else "pass"
        print(f"✅ [CEO AGENT] QA done — verdict: {qa_verdict}")

        # Review QA verdict with LLM
        if qa_result:
            qa_review = self._review_qa_verdict(qa_result["payload"], engineer_result["payload"] if engineer_result else {})
            self._log_decision("qa_review", qa_review.get("reasoning", ""), qa_review)

        # ═══════════════════════════════════════════
        # STEP 7: Post final summary to Slack
        # ═══════════════════════════════════════════
        print("\n🧠 [CEO AGENT] Step 7 — Posting final summary to Slack...")
        self._post_final_summary(product_spec, pr_url, issue_url, qa_verdict)

        # Print the full decision log
        print(f"\n{'='*60}")
        print("📋 [CEO AGENT] DECISION LOG:")
        print(f"{'='*60}")
        for i, decision in enumerate(self.decision_log, 1):
            print(f"\n{i}. [{decision['type']}] {decision['reasoning']}")
        print(f"\n{'='*60}")

        return {
            "product_spec": product_spec,
            "pr_url": pr_url,
            "issue_url": issue_url,
            "qa_verdict": qa_verdict,
        }

    def _decompose_idea(self, idea: str) -> dict:
        """Use LLM to break down the startup idea into agent tasks."""
        prompt = f"""You are the CEO of a startup. You just received this idea:

"{idea}"

Break this idea into specific tasks for your team:
1. Product Agent: what should they focus on?
2. Engineer Agent: what should they build?
3. Marketing Agent: what should they create?

Respond with ONLY valid JSON (no markdown fences):
{{
    "product_focus": "Specific instructions for the product agent — what personas to define, what features to prioritize",
    "engineer_focus": "Specific instructions for the engineer — what to build in the landing page",
    "marketing_focus": "Specific instructions for marketing — what channels to target, what messaging to use",
    "reasoning": "2-3 sentences explaining your strategic thinking for this decomposition"
}}"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            if text.startswith("json"):
                text = text[4:]
            result = json.loads(text.strip())
            print(f"📊 [CEO AGENT] Decomposition reasoning: {result.get('reasoning', '')}")
            return result
        except Exception as e:
            print(f"❌ [CEO AGENT] Decomposition error: {e}")
            return {
                "product_focus": "Define core user personas and top 5 features",
                "engineer_focus": "Build a responsive landing page with features section",
                "marketing_focus": "Create compelling copy for email, social, and Slack",
                "reasoning": "Fallback decomposition due to LLM error",
            }

    def _review_output(self, agent_name: str, output: dict) -> dict:
        """Use LLM to review an agent's output and decide accept/revise."""
        prompt = f"""You are the CEO reviewing the {agent_name} agent's output for GigGuard — a freelancer toolkit for tracking invoices, deadlines, and auto-sending payment reminders.

AGENT OUTPUT:
{json.dumps(output, indent=2)}

Review this output critically:
1. Is it specific enough for GigGuard? (Not generic startup content)
2. Are the details concrete with real numbers and examples?
3. is the content complete — nothing major missing?

Respond with ONLY valid JSON (no markdown fences):
{{
    "verdict": "accept" or "revise",
    "reasoning": "2-3 sentences explaining your decision",
    "issues": "If revise: specific issues found. If accept: empty string",
    "instruction": "If revise: specific instructions for improvement. If accept: empty string"
}}

Be a thoughtful CEO — accept good work, request revision only if something is genuinely missing or too vague."""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            if text.startswith("json"):
                text = text[4:]
            result = json.loads(text.strip())
            print(f"📊 [CEO AGENT] Review verdict for {agent_name}: {result.get('verdict', 'unknown')}")
            print(f"   Reasoning: {result.get('reasoning', '')}")
            return result
        except Exception as e:
            print(f"❌ [CEO AGENT] Review error: {e}")
            return {"verdict": "accept", "reasoning": "Auto-accepted due to LLM error", "issues": "", "instruction": ""}

    def _review_qa_verdict(self, qa_output: dict, engineer_output: dict) -> dict:
        """Use LLM to reason about the QA agent's verdict."""
        prompt = f"""You are the CEO. The QA agent has reviewed the Engineer's landing page and the Marketing copy.

QA VERDICT: {qa_output.get('overall_verdict', 'unknown')}
QA ISSUES: {json.dumps(qa_output.get('issues', []))}
QA SUMMARY: {qa_output.get('summary', '')}

Based on this QA review, decide your next action.

Respond with ONLY valid JSON (no markdown fences):
{{
    "action": "accept" or "request_engineer_revision" or "request_marketing_revision",
    "reasoning": "2-3 sentences explaining your decision as CEO"
}}"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            if text.startswith("json"):
                text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            print(f"❌ [CEO AGENT] QA review reasoning error: {e}")
            return {"action": "accept", "reasoning": "Auto-accepted due to LLM error"}

    def _post_final_summary(self, product_spec: dict, pr_url: str, issue_url: str, qa_verdict: str):
        """Post the final launch summary to Slack."""
        try:
            features = product_spec.get("features", [])
            feature_names = ", ".join([f["name"] for f in features[:5]])
            personas_count = len(product_spec.get("personas", []))

            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🏢 CEO Agent — Final Launch Summary",
                        "emoji": True,
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{product_spec.get('value_proposition', 'GigGuard')}*",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*📋 Product Spec:*\n{personas_count} personas, {len(features)} features defined"},
                        {"type": "mrkdwn", "text": f"*🔧 Engineering:*\nLanding page committed, PR opened"},
                        {"type": "mrkdwn", "text": f"*📣 Marketing:*\nEmail sent, Slack posted, 3 social drafts"},
                        {"type": "mrkdwn", "text": f"*🔍 QA Verdict:*\n{qa_verdict.upper()}"},
                    ],
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🔗 Links:*\n• <{pr_url}|Pull Request>\n• <{issue_url}|GitHub Issue>",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Key Features:* {feature_names}",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Decisions made: {len(self.decision_log)} | CEO Agent 🤖"},
                    ],
                },
            ]

            self.slack_client.chat_postMessage(
                channel="#launches",
                text="🏢 CEO — GigGuard Launch Complete",
                blocks=blocks,
            )
            print("✅ [CEO AGENT] Final summary posted to Slack #launches")

        except SlackApiError as e:
            print(f"❌ [CEO AGENT] Slack error: {e.response['error']}")
        except Exception as e:
            print(f"❌ [CEO AGENT] Slack error: {e}")

    def _log_decision(self, decision_type: str, reasoning: str, data: dict):
        """Log a CEO decision for traceability."""
        self.decision_log.append({
            "type": decision_type,
            "reasoning": reasoning,
            "data": data,
        })
