"""
LaunchMind GigGuard - QA / Reviewer Agent
Reviews Engineer HTML and Marketing copy, posts GitHub review comments,
and sends a pass/fail verdict to the CEO.
"""

import json
import os
import re

import requests
from dotenv import load_dotenv

from llm_helper import call_llm_json

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_REPO_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO_NAME")
GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "QAAgent <qa@launchmind.ai>",
}


class QAAgent:
    """The QA agent reviews the landing page and marketing copy against the spec."""

    def __init__(self, message_bus):
        self.name = "qa"
        self.bus = message_bus

    def run(
        self,
        engineer_output: dict,
        marketing_output: dict,
        product_spec: dict,
        review_scope: str = "full",
        previous_html_review: dict | None = None,
        previous_marketing_review: dict | None = None,
    ):
        print("\n🔍 [QA AGENT] Starting review...")

        html_content = engineer_output.get("html_content", "")
        pr_url = engineer_output.get("github_pr_url", "")

        if not html_content or not pr_url or marketing_output.get("status") != "completed":
            failure_issues = []
            if not html_content:
                failure_issues.append("Engineer output is missing HTML content.")
            if not pr_url:
                failure_issues.append("Engineer output is missing a GitHub PR URL.")
            if marketing_output.get("status") != "completed":
                failure_issues.append("Marketing output is incomplete.")
            payload = {
                "status": "review_complete",
                "overall_verdict": "fail",
                "html_review": {
                    "verdict": "fail",
                    "score": 0,
                    "issues": failure_issues,
                    "strengths": [],
                    "suggestions": ["Complete the required engineering and marketing outputs before QA review."],
                },
                "marketing_review": {
                    "verdict": "fail",
                    "score": 0,
                    "issues": failure_issues,
                    "strengths": [],
                    "suggestions": ["Complete the required engineering and marketing outputs before QA review."],
                },
                "issues": failure_issues,
                "summary": f"QA review could not proceed. Found {len(failure_issues)} blocking issue(s).",
            }
            self._send_report(payload)
            return

        html_content = self._clean_html(html_content)

        html_review = previous_html_review or self._not_reviewed_payload("HTML review was skipped.")
        marketing_review = previous_marketing_review or self._not_reviewed_payload("Marketing review was skipped.")

        if review_scope in ("full", "html_only"):
            html_review = self._review_html(html_content, product_spec)
            if not html_review:
                html_review = {
                    "verdict": "fail",
                    "score": 0,
                    "issues": ["QA could not review the HTML because the LLM review step failed."],
                    "strengths": [],
                    "suggestions": ["Retry the HTML QA review after the LLM dependency recovers."],
                }
            html_review = self._apply_deterministic_html_checks(html_review, html_content, product_spec)

        if review_scope in ("full", "marketing_only"):
            marketing_review = self._review_marketing(marketing_output, product_spec)
            if not marketing_review:
                marketing_review = {
                    "verdict": "fail",
                    "score": 0,
                    "issues": ["QA could not review the marketing copy because the LLM review step failed."],
                    "strengths": [],
                    "suggestions": ["Retry the marketing QA review after the LLM dependency recovers."],
                }

        print(f"📝 [QA AGENT] HTML review complete - verdict: {html_review.get('verdict', 'unknown')}")
        print(f"📝 [QA AGENT] Marketing review complete - verdict: {marketing_review.get('verdict', 'unknown')}")

        if pr_url:
            self._post_pr_comments(pr_url, html_review, marketing_review)

        overall_verdict = "pass"
        if html_review.get("verdict") == "fail" or marketing_review.get("verdict") == "fail":
            overall_verdict = "fail"

        all_issues = html_review.get("issues", []) + marketing_review.get("issues", [])
        payload = {
            "status": "review_complete",
            "overall_verdict": overall_verdict,
            "html_review": html_review,
            "marketing_review": marketing_review,
            "issues": all_issues,
            "summary": (
                f"QA review complete ({review_scope}). Overall verdict: {overall_verdict}. "
                f"Found {len(all_issues)} issue(s)."
            ),
        }
        self._send_report(payload)

    def _review_html(self, html_content: str, product_spec: dict) -> dict:
        prompt = f"""You are a QA reviewer. Review this HTML landing page against the product spec.

PRODUCT SPEC:
{json.dumps(product_spec, indent=2)}

HTML LANDING PAGE:
{html_content}

Check:
1. Does the headline match the value proposition?
2. Are all 5 features from the spec mentioned?
3. Are the personas or their pain points referenced?
4. Is there a clear CTA button?
5. Is the HTML well-structured?

Respond with ONLY valid JSON:
{{
    "verdict": "pass" or "fail",
    "score": 1,
    "issues": ["issue"],
    "strengths": ["strength"],
    "suggestions": ["suggestion"]
}}"""
        return call_llm_json(prompt, agent_name=self.name)

    def _review_marketing(self, marketing_output: dict, product_spec: dict) -> dict:
        prompt = f"""You are a QA reviewer. Review this marketing content against the product spec.

PRODUCT SPEC:
{json.dumps(product_spec, indent=2)}

MARKETING CONTENT:
- Tagline: {marketing_output.get("tagline", "")}
- Description: {marketing_output.get("product_description", "")}
- Email subject: {marketing_output.get("cold_email", {}).get("subject", "")}
- Email body: {marketing_output.get("cold_email", {}).get("body", "")[:1000]}

Check:
1. Is the tagline under 10 words and compelling?
2. Does the description match the value proposition?
3. Does the cold email have a clear CTA?
4. Is the tone appropriate?

Respond with ONLY valid JSON:
{{
    "verdict": "pass" or "fail",
    "score": 1,
    "issues": ["issue"],
    "strengths": ["strength"],
    "suggestions": ["suggestion"]
}}"""
        return call_llm_json(prompt, agent_name=self.name)

    def _post_pr_comments(self, pr_url: str, html_review: dict, marketing_review: dict):
        try:
            pr_number = pr_url.rstrip("/").split("/")[-1]
            comment_body = f"""## QA Agent Review

### HTML Landing Page Review
- Verdict: {html_review.get("verdict", "N/A").upper()}
- Score: {html_review.get("score", "N/A")}/10

Issues:
{self._format_list(html_review.get("issues", []))}

Suggestions:
{self._format_list(html_review.get("suggestions", []))}

### Marketing Copy Review
- Verdict: {marketing_review.get("verdict", "N/A").upper()}
- Score: {marketing_review.get("score", "N/A")}/10

Issues:
{self._format_list(marketing_review.get("issues", []))}

Suggestions:
{self._format_list(marketing_review.get("suggestions", []))}
"""
            issue_comment_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues/{pr_number}/comments"
            requests.post(
                issue_comment_url,
                headers=GITHUB_HEADERS,
                json={"body": comment_body},
                timeout=30,
            )

            files_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{pr_number}/files"
            files_resp = requests.get(files_url, headers=GITHUB_HEADERS, timeout=30)
            if files_resp.status_code != 200:
                return

            changed_files = files_resp.json()
            if not any(file_info.get("filename") == "index.html" for file_info in changed_files):
                return

            pr_info_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{pr_number}"
            pr_resp = requests.get(pr_info_url, headers=GITHUB_HEADERS, timeout=30)
            if pr_resp.status_code != 200:
                return

            commit_sha = pr_resp.json()["head"]["sha"]
            suggestions = html_review.get("suggestions", []) or ["Tighten the hero copy to match the value proposition."]
            review_data = {
                "commit_id": commit_sha,
                "body": "QA Agent automated review",
                "event": "COMMENT",
                "comments": [
                    {
                        "body": f"QA check: HTML verdict is {html_review.get('verdict', 'N/A').upper()}.",
                        "path": "index.html",
                        "line": 1,
                        "side": "RIGHT",
                    },
                    {
                        "body": f"Suggestion: {suggestions[0]}",
                        "path": "index.html",
                        "line": 5,
                        "side": "RIGHT",
                    },
                ],
            }
            review_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{pr_number}/reviews"
            requests.post(review_url, headers=GITHUB_HEADERS, json=review_data, timeout=30)
            print("💬 [QA AGENT] Review comments posted on GitHub PR.")
        except Exception as exc:
            print(f"❌ [QA AGENT] PR comment error: {exc}")

    def _send_report(self, payload: dict):
        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="result",
            payload=payload,
        )
        print(f"📤 [QA AGENT] Review report sent to CEO - verdict: {payload.get('overall_verdict', 'fail')}")

    def _format_list(self, items: list) -> str:
        if not items:
            return "- None"
        return "\n".join(f"- {item}" for item in items)

    def _not_reviewed_payload(self, reason: str) -> dict:
        return {
            "verdict": "pass",
            "score": 10,
            "issues": [],
            "strengths": [reason],
            "suggestions": [],
        }

    def _clean_html(self, html_content: str) -> str:
        cleaned = html_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        if cleaned.lower().startswith("html"):
            cleaned = cleaned[4:]
        return cleaned.strip()

    def _apply_deterministic_html_checks(self, html_review: dict, html_content: str, product_spec: dict) -> dict:
        reviewed = dict(html_review)
        reviewed.setdefault("issues", [])
        reviewed.setdefault("strengths", [])
        reviewed.setdefault("suggestions", [])

        html_lower = html_content.lower()
        missing_features = [
            feature.get("name", "")
            for feature in product_spec.get("features", [])
            if feature.get("name") and feature.get("name", "").lower() not in html_lower
        ]
        missing_personas = [
            persona.get("name", "")
            for persona in product_spec.get("personas", [])
            if persona.get("name") and persona.get("name", "").lower() not in html_lower
        ]
        missing_pain_points = [
            persona.get("name", "")
            for persona in product_spec.get("personas", [])
            if persona.get("pain_point")
            and not self._pain_point_present(persona.get("pain_point", ""), html_lower)
        ]
        has_cta = "start free trial" in html_lower

        deterministic_issues = []
        deterministic_strengths = []

        if missing_features:
            deterministic_issues.append(
                f"Deterministic check: missing feature names in HTML: {', '.join(missing_features)}."
            )
        else:
            deterministic_strengths.append("Deterministic check: all 5 feature names appear in the HTML.")

        if missing_personas:
            deterministic_issues.append(
                f"Deterministic check: missing persona names in HTML: {', '.join(missing_personas)}."
            )
        else:
            deterministic_strengths.append("Deterministic check: all persona names appear in the HTML.")

        if missing_pain_points:
            deterministic_issues.append(
                "Deterministic check: persona pain points are not clearly represented for "
                f"{', '.join(missing_pain_points)}."
            )
        else:
            deterministic_strengths.append("Deterministic check: persona pain points are represented in the HTML.")

        if not has_cta:
            deterministic_issues.append("Deterministic check: CTA text 'Start Free Trial' is missing.")
        else:
            deterministic_strengths.append("Deterministic check: CTA text 'Start Free Trial' is present.")

        reviewed["issues"] = deterministic_issues + reviewed["issues"]
        reviewed["strengths"] = deterministic_strengths + reviewed["strengths"]

        if deterministic_issues:
            reviewed["verdict"] = "fail"
        elif reviewed.get("verdict") == "fail":
            llm_only_issues = [
                issue for issue in reviewed["issues"]
                if not issue.startswith("Deterministic check:")
            ]
            if not llm_only_issues:
                reviewed["verdict"] = "pass"
                reviewed["issues"] = []

        return reviewed

    def _pain_point_present(self, pain_point: str, html_lower: str) -> bool:
        normalized_words = self._tokenize_meaningful_words(pain_point)
        if not normalized_words:
            return False

        html_words = set(self._tokenize_meaningful_words(html_lower))
        overlap = html_words.intersection(normalized_words)

        # Accept paraphrases when enough of the core concepts appear.
        min_required = min(3, max(2, len(normalized_words) // 4))
        return len(overlap) >= min_required

    def _tokenize_meaningful_words(self, text: str) -> list[str]:
        stop_words = {
            "a", "an", "and", "are", "as", "at", "be", "because", "by", "can", "currently",
            "due", "for", "from", "has", "have", "he", "her", "him", "his", "if", "in", "into",
            "is", "it", "its", "like", "means", "month", "monthly", "of", "often", "on", "or",
            "per", "quarter", "she", "so", "spends", "that", "the", "their", "them", "they",
            "this", "through", "to", "up", "uses", "using", "week", "with", "you"
        }
        words = re.findall(r"[a-zA-Z]{4,}", text.lower())
        return [word for word in words if word not in stop_words]
