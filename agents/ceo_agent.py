"""
LaunchMind GigGuard - CEO Agent (Orchestrator)
Decomposes the startup idea into tasks, dispatches them to sub-agents,
reviews outputs, handles revisions, and posts the final summary.
"""

import json
import os

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from llm_helper import call_llm_json

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")


class CEOAgent:
    """The CEO agent orchestrates the entire pipeline."""

    def __init__(self, message_bus):
        self.name = "ceo"
        self.bus = message_bus
        self.slack_client = WebClient(token=SLACK_BOT_TOKEN)
        self.decision_log = []

    def run(self, startup_idea: str):
        print("\n🏢 [CEO AGENT] Starting orchestration...")
        print(f"💡 Startup Idea: {startup_idea}\n")

        print("🧠 [CEO AGENT] Step 1 - Decomposing idea into tasks via LLM...")
        tasks = self._decompose_idea(startup_idea)
        if not tasks:
            tasks = self._fallback_tasks()
            self._log_decision("idea_decomposition", "Used fallback task decomposition after LLM failure.", tasks)
            return self._fail_pipeline(
                "CEO could not complete the required LLM task decomposition.",
                tasks=tasks,
            )
        tasks = self._normalize_task_fields(tasks)
        self._log_decision("idea_decomposition", tasks.get("reasoning", ""), tasks)

        print("\n🧠 [CEO AGENT] Step 2 - Dispatching tasks to Product, Engineer, and Marketing agents...")
        product_task_id = self.bus.send(
            from_agent=self.name,
            to_agent="product",
            message_type="task",
            payload={"idea": startup_idea, "focus": tasks["product_focus"]},
        )
        self.bus.send(
            from_agent=self.name,
            to_agent="engineer",
            message_type="task",
            payload={"idea": startup_idea, "focus": tasks["engineer_focus"]},
        )
        self.bus.send(
            from_agent=self.name,
            to_agent="marketing",
            message_type="task",
            payload={"idea": startup_idea, "focus": tasks["marketing_focus"]},
        )

        from agents.product_agent import ProductAgent

        product_agent = ProductAgent(self.bus)
        product_agent.run()

        print("\n🧠 [CEO AGENT] Step 3 - Reviewing Product Agent output via LLM...")
        product_result = self._get_latest_message("product", "confirmation")
        if not product_result or product_result["payload"].get("status") == "failed":
            return self._fail_pipeline(
                "Product Agent failed to produce a valid product spec.",
                tasks=tasks,
            )

        product_spec = product_result["payload"].get("product_spec", {})
        review_result = self._review_output("product", product_spec)
        if not review_result:
            return self._fail_pipeline(
                "CEO could not review the Product Agent output with the LLM.",
                tasks=tasks,
                product_spec=product_spec,
            )

        self._log_decision("product_review", review_result["reasoning"], review_result)
        if review_result.get("verdict") == "revise":
            print("🔄 [CEO AGENT] Requesting revision from Product Agent...")
            self.bus.send(
                from_agent=self.name,
                to_agent="product",
                message_type="revision_request",
                payload={
                    "issue": review_result.get("issues", ""),
                    "instruction": review_result.get("instruction", ""),
                    "original_spec": product_spec,
                    "product_spec": product_spec,
                },
                parent_message_id=product_result["message_id"],
            )
            revision_msg = self.bus.receive("product")[-1]
            product_agent.handle_revision(revision_msg)
            revised_result = self._get_latest_message("product", "confirmation")
            if not revised_result or revised_result["payload"].get("status") == "failed":
                return self._fail_pipeline(
                    "Product Agent revision failed.",
                    tasks=tasks,
                    product_spec=product_spec,
                )
            product_spec = revised_result["payload"].get("product_spec", product_spec)
            self._log_decision("product_revision_accepted", "Accepted revised product spec.", {"revised": True})
            print("✅ [CEO AGENT] Revised product spec accepted.")
        else:
            print("✅ [CEO AGENT] Product spec approved - no revision needed.")

        print("\n🧠 [CEO AGENT] Step 4 - Running Engineer Agent...")
        from agents.engineer_agent import EngineerAgent

        engineer_agent = EngineerAgent(self.bus)
        engineer_agent.run()
        engineer_result = self._get_latest_message("engineer", "result")
        if not engineer_result or engineer_result["payload"].get("status") != "completed":
            return self._fail_pipeline(
                "Engineer Agent failed to produce the GitHub issue, commit, and PR.",
                tasks=tasks,
                product_spec=product_spec,
                engineer_result=engineer_result["payload"] if engineer_result else {},
            )

        engineer_payload = engineer_result["payload"]
        pr_url = engineer_payload.get("github_pr_url", "")
        issue_url = engineer_payload.get("github_issue_url", "")
        print(f"✅ [CEO AGENT] Engineer done - PR: {pr_url}")

        print("\n🧠 [CEO AGENT] Step 5 - Running Marketing Agent...")
        from agents.marketing_agent import MarketingAgent

        marketing_agent = MarketingAgent(self.bus)
        marketing_agent.run(pr_url=pr_url)
        marketing_result = self._get_latest_message("marketing", "result")
        if not marketing_result or marketing_result["payload"].get("status") != "completed":
            return self._fail_pipeline(
                "Marketing Agent failed to send the required email or Slack post.",
                tasks=tasks,
                product_spec=product_spec,
                engineer_result=engineer_payload,
                marketing_result=marketing_result["payload"] if marketing_result else {},
            )
        marketing_payload = marketing_result["payload"]
        print("✅ [CEO AGENT] Marketing done.")

        print("\n🧠 [CEO AGENT] Step 6 - Running QA Agent...")
        from agents.qa_agent import QAAgent

        qa_agent = QAAgent(self.bus)
        qa_agent.run(
            engineer_output=engineer_payload,
            marketing_output=marketing_payload,
            product_spec=product_spec,
            review_scope="full",
        )
        qa_result = self._get_latest_message("qa", "result")
        if not qa_result:
            return self._fail_pipeline(
                "QA Agent did not return a review report.",
                tasks=tasks,
                product_spec=product_spec,
                engineer_result=engineer_payload,
                marketing_result=marketing_payload,
            )

        qa_payload = qa_result["payload"]
        qa_verdict = qa_payload.get("overall_verdict", "fail")
        print(f"✅ [CEO AGENT] QA done - verdict: {qa_verdict}")

        qa_review = self._review_qa_verdict(qa_payload, engineer_payload, marketing_payload)
        if not qa_review:
            return self._fail_pipeline(
                "CEO could not reason about the QA verdict with the LLM.",
                tasks=tasks,
                product_spec=product_spec,
                engineer_result=engineer_payload,
                marketing_result=marketing_payload,
                qa_result=qa_payload,
            )
        self._log_decision("qa_review", qa_review.get("reasoning", ""), qa_review)

        if qa_payload.get("overall_verdict") == "fail":
            action = qa_review.get("action")
            issue_text = "\n".join(qa_payload.get("issues", []))

            if action == "request_engineer_revision":
                self.bus.send(
                    from_agent=self.name,
                    to_agent="engineer",
                    message_type="revision_request",
                    payload={
                        "issue": issue_text,
                        "instruction": "Revise the landing page to address the QA issues.",
                        "product_spec": product_spec,
                        "github_pr_url": pr_url,
                        "github_issue_url": issue_url,
                    },
                    parent_message_id=engineer_result["message_id"],
                )
                revision_msg = self.bus.receive("engineer")[-1]
                engineer_agent.handle_revision(revision_msg)
                engineer_result = self._get_latest_message("engineer", "result")
                if not engineer_result or engineer_result["payload"].get("status") != "completed":
                    return self._fail_pipeline(
                        "Engineer Agent revision failed after QA feedback.",
                        tasks=tasks,
                        product_spec=product_spec,
                        engineer_result=engineer_result["payload"] if engineer_result else {},
                        marketing_result=marketing_payload,
                        qa_result=qa_payload,
                    )
                engineer_payload = engineer_result["payload"]
                pr_url = engineer_payload.get("github_pr_url", pr_url)
                issue_url = engineer_payload.get("github_issue_url", issue_url)
                self._log_decision("qa_revision", "Requested Engineer revision after QA fail.", {"target": "engineer"})
            elif action == "request_marketing_revision":
                self.bus.send(
                    from_agent=self.name,
                    to_agent="marketing",
                    message_type="revision_request",
                    payload={
                        "issue": issue_text,
                        "instruction": "Revise the marketing copy to address the QA issues.",
                        "product_spec": product_spec,
                    },
                    parent_message_id=marketing_result["message_id"],
                )
                revision_msg = self.bus.receive("marketing")[-1]
                marketing_agent.handle_revision(revision_msg, pr_url=pr_url)
                marketing_result = self._get_latest_message("marketing", "result")
                if not marketing_result or marketing_result["payload"].get("status") != "completed":
                    return self._fail_pipeline(
                        "Marketing Agent revision failed after QA feedback.",
                        tasks=tasks,
                        product_spec=product_spec,
                        engineer_result=engineer_payload,
                        marketing_result=marketing_result["payload"] if marketing_result else {},
                        qa_result=qa_payload,
                    )
                marketing_payload = marketing_result["payload"]
                self._log_decision("qa_revision", "Requested Marketing revision after QA fail.", {"target": "marketing"})
            else:
                return self._fail_pipeline(
                    "QA failed and the CEO could not select a valid revision action.",
                    tasks=tasks,
                    product_spec=product_spec,
                    engineer_result=engineer_payload,
                    marketing_result=marketing_payload,
                    qa_result=qa_payload,
                )

            qa_agent.run(
                engineer_output=engineer_payload,
                marketing_output=marketing_payload,
                product_spec=product_spec,
                review_scope="html_only" if action == "request_engineer_revision" else "marketing_only",
                previous_html_review=qa_payload.get("html_review"),
                previous_marketing_review=qa_payload.get("marketing_review"),
            )
            qa_result = self._get_latest_message("qa", "result")
            qa_payload = qa_result["payload"] if qa_result else {}
            qa_verdict = qa_payload.get("overall_verdict", "fail")
            if qa_verdict != "pass":
                return self._fail_pipeline(
                    "QA still failed after the revision loop.",
                    tasks=tasks,
                    product_spec=product_spec,
                    engineer_result=engineer_payload,
                    marketing_result=marketing_payload,
                    qa_result=qa_payload,
                )

        print("\n🧠 [CEO AGENT] Step 7 - Posting final summary to Slack...")
        slack_ok = self._post_final_summary(product_spec, pr_url, issue_url, qa_verdict)
        if not slack_ok:
            return self._fail_pipeline(
                "CEO could not post the final summary to Slack.",
                tasks=tasks,
                product_spec=product_spec,
                engineer_result=engineer_payload,
                marketing_result=marketing_payload,
                qa_result=qa_payload,
            )

        self._print_decision_log()
        return {
            "status": "completed",
            "product_spec": product_spec,
            "pr_url": pr_url,
            "issue_url": issue_url,
            "qa_verdict": qa_verdict,
            "decision_log": self.decision_log,
        }

    def _decompose_idea(self, idea: str) -> dict:
        prompt = f"""You are the CEO of a startup. You just received this idea:

"{idea}"

Break this idea into specific tasks for your team:
1. Product Agent
2. Engineer Agent
3. Marketing Agent

Respond with ONLY valid JSON:
{{
    "product_focus": "Specific instructions for the product agent",
    "engineer_focus": "Specific instructions for the engineer agent",
    "marketing_focus": "Specific instructions for the marketing agent",
    "reasoning": "2-3 sentences of strategic reasoning"
}}"""
        return call_llm_json(prompt, agent_name=self.name)

    def _review_output(self, agent_name: str, output: dict) -> dict:
        prompt = f"""You are the CEO reviewing the {agent_name} agent's output for GigGuard.

AGENT OUTPUT:
{json.dumps(output, indent=2)}

Respond with ONLY valid JSON:
{{
    "verdict": "accept" or "revise",
    "reasoning": "2-3 sentences",
    "issues": "Specific issues or empty string",
    "instruction": "Concrete revision instructions or empty string"
}}"""
        return call_llm_json(prompt, agent_name=self.name)

    def _review_qa_verdict(self, qa_output: dict, engineer_output: dict, marketing_output: dict) -> dict:
        prompt = f"""You are the CEO. The QA agent has reviewed the Engineer and Marketing outputs.

QA OUTPUT:
{json.dumps(qa_output, indent=2)}

ENGINEER SUMMARY:
{engineer_output.get("summary", "")}

MARKETING SUMMARY:
{marketing_output.get("summary", "")}

Respond with ONLY valid JSON:
{{
    "action": "accept" or "request_engineer_revision" or "request_marketing_revision",
    "reasoning": "2-3 sentences"
}}"""
        return call_llm_json(prompt, agent_name=self.name)

    def _post_final_summary(self, product_spec: dict, pr_url: str, issue_url: str, qa_verdict: str) -> bool:
        try:
            features = product_spec.get("features", [])
            feature_names = ", ".join(feature.get("name", "") for feature in features[:5])
            personas_count = len(product_spec.get("personas", []))
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🏢 CEO Agent - Final Launch Summary", "emoji": True},
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{product_spec.get('value_proposition', 'GigGuard')}*"},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Product Spec:*\n{personas_count} personas, {len(features)} features"},
                        {"type": "mrkdwn", "text": "*Engineering:*\nIssue, commit, and PR completed"},
                        {"type": "mrkdwn", "text": "*Marketing:*\nEmail sent and Slack post published"},
                        {"type": "mrkdwn", "text": f"*QA Verdict:*\n{qa_verdict.upper()}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Links:*\n• <{pr_url}|Pull Request>\n• <{issue_url}|GitHub Issue>"},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Key Features:* {feature_names}"},
                },
            ]
            self.slack_client.chat_postMessage(
                channel="#launches",
                text="CEO - GigGuard Launch Complete",
                blocks=blocks,
            )
            print("✅ [CEO AGENT] Final summary posted to Slack #launches")
            return True
        except SlackApiError as exc:
            print(f"❌ [CEO AGENT] Slack error: {exc.response['error']}")
            return False
        except Exception as exc:
            print(f"❌ [CEO AGENT] Slack error: {exc}")
            return False

    def _get_latest_message(self, from_agent: str, message_type: str):
        history = self.bus.get_history(self.name)
        matches = [
            message for message in history
            if message["from_agent"] == from_agent and message["message_type"] == message_type
        ]
        return matches[-1] if matches else None

    def _fallback_tasks(self):
        return {
            "product_focus": "Define core user personas and top 5 features for GigGuard.",
            "engineer_focus": "Build a responsive landing page that clearly explains the freelancer invoice workflow.",
            "marketing_focus": "Create launch messaging focused on freelancers who struggle with invoices and reminders.",
            "reasoning": "Fallback decomposition.",
        }

    def _normalize_task_fields(self, tasks: dict) -> dict:
        normalized = dict(tasks)
        for key in ("product_focus", "engineer_focus", "marketing_focus"):
            value = normalized.get(key, "")
            if isinstance(value, list):
                normalized[key] = "\n".join(f"- {item}" for item in value)
            elif isinstance(value, dict):
                normalized[key] = json.dumps(value, indent=2)
            else:
                normalized[key] = str(value)
        return normalized

    def _fail_pipeline(self, reason: str, **data):
        self._log_decision("pipeline_failure", reason, data)
        self._print_decision_log()
        return {
            "status": "failed",
            "product_spec": data.get("product_spec", {}),
            "pr_url": data.get("engineer_result", {}).get("github_pr_url", ""),
            "issue_url": data.get("engineer_result", {}).get("github_issue_url", ""),
            "qa_verdict": data.get("qa_result", {}).get("overall_verdict", "fail"),
            "error": reason,
            "decision_log": self.decision_log,
        }

    def _print_decision_log(self):
        print(f"\n{'=' * 60}")
        print("📋 [CEO AGENT] DECISION LOG:")
        print(f"{'=' * 60}")
        for index, decision in enumerate(self.decision_log, start=1):
            print(f"\n{index}. [{decision['type']}] {decision['reasoning']}")
        print(f"\n{'=' * 60}")

    def _log_decision(self, decision_type: str, reasoning: str, data: dict):
        self.decision_log.append(
            {
                "type": decision_type,
                "reasoning": reasoning,
                "data": data,
            }
        )
