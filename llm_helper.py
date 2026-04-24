"""
LaunchMind GigGuard - LLM Helper
Shared Gemini API wrapper with automatic retry logic for rate limiting.
"""

import json
import os
import re
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

_client = None
DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash-lite")


def get_client():
    """Get or create the shared Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _extract_retry_delay_seconds(error_str: str) -> int | None:
    """Extract provider retry delay when it is present in the error text."""
    match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", error_str, flags=re.IGNORECASE)
    if match:
        return max(1, int(float(match.group(1))))
    return None


def call_llm(prompt: str, agent_name: str = "agent", max_retries: int = 3) -> str:
    """
    Call Gemini with retry support for quota and rate-limit errors.

    Returns the raw response text, or None if all retries fail.
    """
    client = get_client()

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=DEFAULT_LLM_MODEL,
                contents=prompt,
            )
            return response.text
        except Exception as exc:
            error_str = str(exc)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait_time = _extract_retry_delay_seconds(error_str) or (15 * (attempt + 1))
                print(
                    f"⏳ [{agent_name.upper()}] Rate limited. Waiting {wait_time}s before retry "
                    f"({attempt + 1}/{max_retries})..."
                )
                time.sleep(wait_time)
                continue

            print(f"❌ [{agent_name.upper()}] LLM error: {exc}")
            return None

    print(f"❌ [{agent_name.upper()}] All {max_retries} retries exhausted.")
    return None


def parse_json_response(text: str):
    """Parse JSON from an LLM response, handling fences and surrounding text."""
    if not text:
        return None

    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:]

    cleaned = text.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    object_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if object_match:
        try:
            return json.loads(object_match.group(0).strip())
        except json.JSONDecodeError:
            pass

    array_match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0).strip())
        except json.JSONDecodeError:
            pass

    return None


def call_llm_json(prompt: str, agent_name: str = "agent", max_retries: int = 3):
    """Call the LLM and parse the response as JSON."""
    response_text = call_llm(prompt, agent_name=agent_name, max_retries=max_retries)
    if not response_text:
        return None

    parsed = parse_json_response(response_text)
    if parsed is None:
        preview = response_text.strip().replace("\n", " ")[:500]
        print(f"❌ [{agent_name.upper()}] Failed to parse LLM JSON response.")
        print(f"🪵 [{agent_name.upper()}] Raw response preview: {preview}")
    return parsed
