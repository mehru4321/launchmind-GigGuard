"""
LaunchMind GigGuard - Product Agent
Generates a structured product specification from the startup idea.
"""

import json

from llm_helper import call_llm_json


class ProductAgent:
    """
    The Product agent thinks like a product manager.
    It receives a task from the CEO and produces a structured product spec.
    """

    def __init__(self, message_bus):
        self.name = "product"
        self.bus = message_bus

    def run(self):
        """Receive the CEO task, generate the product spec, and distribute it."""
        print("\n🧠 [PRODUCT AGENT] Starting...")

        task_msg = self._get_latest_message("task")
        if not task_msg:
            print("❌ [PRODUCT AGENT] No task received from CEO.")
            self._send_failure("No task received from CEO.", parent_message_id=None)
            return

        idea = task_msg["payload"].get("idea", "")
        focus = task_msg["payload"].get("focus", "")
        print(f"📋 [PRODUCT AGENT] Received task - Idea: {idea[:80]}...")

        product_spec = self._generate_product_spec(idea, focus)
        product_spec = self._normalize_product_spec(product_spec)
        validation_error = self._get_product_spec_validation_error(product_spec)
        if validation_error:
            print("❌ [PRODUCT AGENT] Failed to generate a valid product spec.")
            print(f"🪵 [PRODUCT AGENT] Validation error: {validation_error}")
            print("🪵 [PRODUCT AGENT] Normalized product spec preview:")
            print(json.dumps(product_spec, indent=2)[:4000])
            self._send_failure(
                f"LLM did not return a valid product spec. {validation_error}",
                parent_message_id=task_msg["message_id"],
            )
            return

        print("✅ [PRODUCT AGENT] Product spec generated successfully.")

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
        """Revise the product spec based on CEO feedback."""
        print("\n🔄 [PRODUCT AGENT] Received revision request...")

        feedback = revision_msg["payload"].get("issue", "")
        instruction = revision_msg["payload"].get("instruction", "")
        original_spec = revision_msg["payload"].get("original_spec", {})

        revised_spec = self._revise_product_spec(original_spec, feedback, instruction)
        revised_spec = self._normalize_product_spec(revised_spec)
        validation_error = self._get_product_spec_validation_error(revised_spec)
        if validation_error:
            print("❌ [PRODUCT AGENT] Failed to revise product spec.")
            print(f"🪵 [PRODUCT AGENT] Validation error: {validation_error}")
            print("🪵 [PRODUCT AGENT] Normalized revised spec preview:")
            print(json.dumps(revised_spec, indent=2)[:4000])
            self._send_failure(
                f"LLM did not return a valid revised product spec. {validation_error}",
                parent_message_id=revision_msg["message_id"],
            )
            return

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

    def _get_latest_message(self, message_type: str):
        messages = self.bus.receive(self.name)
        filtered = [msg for msg in messages if msg["message_type"] == message_type]
        return filtered[-1] if filtered else None

    def _generate_product_spec(self, idea: str, focus: str) -> dict:
        focus_text = self._normalize_focus(focus)
        prompt = f"""You are a senior product manager. Based on the startup idea below, generate a detailed product specification.

STARTUP IDEA: {idea}
FOCUS AREAS:
{focus_text}

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
}}"""
        return call_llm_json(prompt, agent_name=self.name)

    def _revise_product_spec(self, original_spec: dict, feedback: str, instruction: str) -> dict:
        prompt = f"""You are a senior product manager. The CEO reviewed your product spec and wants revisions.

ORIGINAL SPEC:
{json.dumps(original_spec, indent=2)}

CEO FEEDBACK: {feedback}
CEO INSTRUCTION: {instruction}

Revise the product spec addressing all the feedback. Respond with ONLY valid JSON in the same format as the original spec."""
        return call_llm_json(prompt, agent_name=self.name)

    def _get_product_spec_validation_error(self, product_spec: dict) -> str | None:
        if not isinstance(product_spec, dict):
            return "Response is not a JSON object."

        value_proposition = product_spec.get("value_proposition")
        personas = product_spec.get("personas", [])
        features = product_spec.get("features", [])
        user_stories = product_spec.get("user_stories", [])

        if not isinstance(value_proposition, str) or not value_proposition.strip():
            return "Missing or empty value_proposition."
        if not isinstance(personas, list) or not (2 <= len(personas) <= 3):
            return "Personas must be an array with 2 or 3 entries."
        if not all(isinstance(persona, dict) for persona in personas):
            return "Each persona must be an object."
        if not all(persona.get("name") and persona.get("role") and persona.get("pain_point") for persona in personas):
            return "Each persona must include name, role, and pain_point."
        if not isinstance(features, list) or len(features) != 5:
            return "Features must be an array with exactly 5 entries."
        if not all(isinstance(feature, dict) for feature in features):
            return "Each feature must be an object."
        if not all(
            feature.get("name") and feature.get("description") and isinstance(feature.get("priority"), int)
            for feature in features
        ):
            return "Each feature must include name, description, and integer priority."
        if not isinstance(user_stories, list) or len(user_stories) != 3:
            return "user_stories must be an array with exactly 3 entries."
        if not all(isinstance(story, str) and story.strip() for story in user_stories):
            return "Each user story must be a non-empty string."
        return None

    def _normalize_product_spec(self, product_spec: dict) -> dict:
        if not isinstance(product_spec, dict):
            return product_spec

        normalized = dict(product_spec)

        if not normalized.get("value_proposition"):
            normalized["value_proposition"] = (
                normalized.get("valueProp")
                or normalized.get("value_prop")
                or normalized.get("product_value")
                or ""
            )

        if "personas" not in normalized:
            normalized["personas"] = normalized.get("user_personas") or normalized.get("target_personas") or []

        if "features" not in normalized:
            normalized["features"] = normalized.get("core_features") or normalized.get("top_features") or []

        if "user_stories" not in normalized:
            normalized["user_stories"] = normalized.get("stories") or normalized.get("userStories") or []

        normalized["personas"] = [self._normalize_persona(persona) for persona in normalized.get("personas", [])]
        normalized["features"] = self._normalize_features(normalized)
        normalized["user_stories"] = self._normalize_user_stories(normalized.get("user_stories", []))

        return normalized

    def _normalize_persona(self, persona: dict) -> dict:
        if not isinstance(persona, dict):
            return persona
        normalized = dict(persona)
        if not normalized.get("pain_point"):
            normalized["pain_point"] = normalized.get("painPoint") or normalized.get("painPoints") or normalized.get("pain") or ""
        return normalized

    def _normalize_feature(self, feature: dict, index: int) -> dict:
        if not isinstance(feature, dict):
            if isinstance(feature, str) and feature.strip():
                return {
                    "name": feature.strip(),
                    "description": feature.strip(),
                    "priority": index,
                }
            return feature
        normalized = dict(feature)
        if not normalized.get("name"):
            normalized["name"] = normalized.get("title") or normalized.get("feature") or normalized.get("feature_name") or ""
        if not normalized.get("description"):
            normalized["description"] = normalized.get("details") or normalized.get("summary") or ""
        priority = normalized.get("priority")
        if isinstance(priority, str) and priority.isdigit():
            normalized["priority"] = int(priority)
        elif priority is None:
            normalized["priority"] = index
        return normalized

    def _normalize_features(self, product_spec: dict) -> list:
        raw_features = (
            product_spec.get("features")
            or product_spec.get("core_features")
            or product_spec.get("top_features")
            or product_spec.get("feature_list")
            or product_spec.get("prioritized_features")
            or []
        )

        if isinstance(raw_features, dict):
            if "items" in raw_features and isinstance(raw_features["items"], list):
                raw_features = raw_features["items"]
            else:
                raw_features = list(raw_features.values())

        if isinstance(raw_features, str):
            raw_features = [
                line.strip(" -•\n\r\t")
                for line in raw_features.splitlines()
                if line.strip()
            ]

        normalized = []
        if isinstance(raw_features, list):
            for index, feature in enumerate(raw_features, start=1):
                normalized_feature = self._normalize_feature(feature, index)
                if isinstance(normalized_feature, dict) and (
                    normalized_feature.get("name") or normalized_feature.get("description")
                ):
                    if not normalized_feature.get("name") and normalized_feature.get("description"):
                        normalized_feature["name"] = normalized_feature["description"][:80]
                    if not normalized_feature.get("description") and normalized_feature.get("name"):
                        normalized_feature["description"] = normalized_feature["name"]
                    normalized.append(normalized_feature)

        deduped = []
        seen = set()
        for index, feature in enumerate(normalized, start=1):
            feature["priority"] = index
            dedupe_key = (feature.get("name", "").strip().lower(), feature.get("description", "").strip().lower())
            if dedupe_key not in seen:
                deduped.append(feature)
                seen.add(dedupe_key)

        return deduped[:5]

    def _normalize_user_stories(self, user_stories) -> list:
        if isinstance(user_stories, str):
            split_stories = [
                part.strip(" -•\n\r\t")
                for part in user_stories.splitlines()
                if part.strip()
            ]
            user_stories = split_stories

        if isinstance(user_stories, dict):
            ordered_values = [value for _, value in sorted(user_stories.items())]
            user_stories = ordered_values

        normalized = []
        if isinstance(user_stories, list):
            for story in user_stories:
                if isinstance(story, str) and story.strip():
                    normalized.append(story.strip())
                    continue

                if isinstance(story, dict):
                    as_a = story.get("as_a") or story.get("asA") or story.get("user") or story.get("role")
                    want = story.get("i_want") or story.get("iWant") or story.get("want") or story.get("action")
                    so_that = story.get("so_that") or story.get("soThat") or story.get("benefit") or story.get("outcome")
                    if as_a and want and so_that:
                        normalized.append(f"As a {as_a}, I want to {want} so that {so_that}")

        deduped = []
        seen = set()
        for story in normalized:
            key = story.lower()
            if key not in seen:
                deduped.append(story)
                seen.add(key)

        return deduped[:3]

    def _normalize_focus(self, focus) -> str:
        if isinstance(focus, list):
            return "\n".join(f"- {item}" for item in focus)
        if isinstance(focus, dict):
            return json.dumps(focus, indent=2)
        return str(focus)

    def _send_failure(self, reason: str, parent_message_id: str | None):
        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="confirmation",
            payload={
                "status": "failed",
                "summary": reason,
                "product_spec": {},
            },
            parent_message_id=parent_message_id,
        )
