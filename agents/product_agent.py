"""
LaunchMind GigGuard — Product Agent
Generates a structured product specification from the startup idea.
"""

import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


class ProductAgent:
    """
    The Product agent thinks like a product manager.
    It receives a task from the CEO and produces a structured product spec
    with value proposition, personas, features, and user stories.
    """

    def __init__(self, message_bus):
        self.name = "product"
        self.bus = message_bus
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def run(self):
        """Main execution loop: receive task, generate spec, send results."""
        print(f"\n🧠 [PRODUCT AGENT] Starting...")

        # 1. Receive task from CEO
        messages = self.bus.receive(self.name)
        task_msg = None
        for m in messages:
            if m["message_type"] == "task":
                task_msg = m
                break

        if not task_msg:
            print("❌ [PRODUCT AGENT] No task received from CEO.")
            return

        idea = task_msg["payload"].get("idea", "")
        focus = task_msg["payload"].get("focus", "")
        print(f"📋 [PRODUCT AGENT] Received task — Idea: {idea[:80]}...")

        # 2. Generate product spec using LLM
        product_spec = self._generate_product_spec(idea, focus)

        if not product_spec:
            print("❌ [PRODUCT AGENT] Failed to generate product spec.")
            return

        print("✅ [PRODUCT AGENT] Product spec generated successfully.")

        # 3. Send product spec to Engineer and Marketing agents
        self.bus.send(
            from_agent=self.name,
            to_agent="engineer",
            message_type="result",
            payload={"product_spec": product_spec},
            parent_message_id=task_msg["message_id"],
        )

        self.bus.send(
            from_agent=self.name,
            to_agent="marketing",
            message_type="result",
            payload={"product_spec": product_spec},
            parent_message_id=task_msg["message_id"],
        )

        # 4. Send confirmation back to CEO
        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="confirmation",
            payload={
                "status": "completed",
                "summary": "Product spec generated and sent to Engineer and Marketing agents.",
                "product_spec": product_spec,
            },
            parent_message_id=task_msg["message_id"],
        )

        print("📤 [PRODUCT AGENT] Spec sent to Engineer, Marketing, and CEO.")

    def handle_revision(self, revision_msg):
        """Handle a revision request from the CEO agent."""
        print(f"\n🔄 [PRODUCT AGENT] Received revision request...")

        feedback = revision_msg["payload"].get("issue", "")
        instruction = revision_msg["payload"].get("instruction", "")
        original_spec = revision_msg["payload"].get("original_spec", {})

        revised_spec = self._revise_product_spec(original_spec, feedback, instruction)

        if not revised_spec:
            print("❌ [PRODUCT AGENT] Failed to revise product spec.")
            return

        # Send revised spec to Engineer and Marketing
        self.bus.send(
            from_agent=self.name,
            to_agent="engineer",
            message_type="result",
            payload={"product_spec": revised_spec},
            parent_message_id=revision_msg["message_id"],
        )

        self.bus.send(
            from_agent=self.name,
            to_agent="marketing",
            message_type="result",
            payload={"product_spec": revised_spec},
            parent_message_id=revision_msg["message_id"],
        )

        # Send confirmation back to CEO
        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="confirmation",
            payload={
                "status": "revised",
                "summary": "Product spec revised based on CEO feedback.",
                "product_spec": revised_spec,
            },
            parent_message_id=revision_msg["message_id"],
        )

        print("✅ [PRODUCT AGENT] Revised spec sent to all agents.")

    def _generate_product_spec(self, idea: str, focus: str) -> dict:
        """Use Gemini to generate the product specification."""
        prompt = f"""You are a senior product manager. Based on the startup idea below, generate a detailed product specification.

STARTUP IDEA: {idea}
FOCUS AREAS: {focus}

You MUST respond with ONLY valid JSON (no markdown, no code fences, no extra text) in this exact format:
{{
    "value_proposition": "One sentence describing what the product does and for whom",
    "personas": [
        {{
            "name": "A realistic full name",
            "role": "Their professional role and context",
            "pain_point": "A specific, detailed pain point with concrete numbers/examples"
        }},
        {{
            "name": "...",
            "role": "...",
            "pain_point": "..."
        }},
        {{
            "name": "...",
            "role": "...",
            "pain_point": "..."
        }}
    ],
    "features": [
        {{
            "name": "Feature name",
            "description": "Detailed feature description",
            "priority": 1
        }},
        {{
            "name": "...",
            "description": "...",
            "priority": 2
        }},
        {{
            "name": "...",
            "description": "...",
            "priority": 3
        }},
        {{
            "name": "...",
            "description": "...",
            "priority": 4
        }},
        {{
            "name": "...",
            "description": "...",
            "priority": 5
        }}
    ],
    "user_stories": [
        "As a [user], I want to [action] so that [benefit]",
        "As a [user], I want to [action] so that [benefit]",
        "As a [user], I want to [action] so that [benefit]"
    ]
}}

Requirements:
- value_proposition: must mention the target user AND the core benefit
- personas: exactly 3, each with a realistic name, specific role, and pain point including concrete details
- features: exactly 5, ranked by priority (1=highest), with clear descriptions
- user_stories: exactly 3, in standard "As a / I want / So that" format
- Make everything specific to GigGuard and freelancers — no generic content"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            # Clean potential markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            if text.startswith("json"):
                text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            print(f"❌ [PRODUCT AGENT] LLM error: {e}")
            return None

    def _revise_product_spec(self, original_spec: dict, feedback: str, instruction: str) -> dict:
        """Use Gemini to revise the product spec based on CEO feedback."""
        prompt = f"""You are a senior product manager. The CEO reviewed your product spec and wants revisions.

ORIGINAL SPEC:
{json.dumps(original_spec, indent=2)}

CEO FEEDBACK: {feedback}
CEO INSTRUCTION: {instruction}

Revise the product spec addressing all the feedback. Respond with ONLY valid JSON (no markdown, no code fences) in the same format as the original spec, with the improvements applied."""

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
            print(f"❌ [PRODUCT AGENT] LLM revision error: {e}")
            return None
