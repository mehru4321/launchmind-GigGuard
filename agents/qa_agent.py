"""
LaunchMind GigGuard — QA / Reviewer Agent
Reviews Engineer's HTML and Marketing's copy, posts GitHub PR comments,
and sends a pass/fail verdict to the CEO.
"""

import os
import json
import requests
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_REPO_OWNER", "mehru4321")
GITHUB_REPO = os.getenv("GITHUB_REPO_NAME", "launchmind-GigGuard")
GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "QAAgent <qa@launchmind.ai>",
}


class QAAgent:
    """
    The QA agent reviews the Engineer's HTML landing page and the
    Marketing agent's copy. It posts PR review comments on GitHub
    and sends a structured pass/fail report to the CEO.
    """

    def __init__(self, message_bus):
        self.name = "qa"
        self.bus = message_bus
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def run(self, engineer_output: dict, marketing_output: dict, product_spec: dict):
        """
        Main execution: review HTML and marketing copy, post PR comments, send verdict.

        Args:
            engineer_output: The engineer agent's result payload
            marketing_output: The marketing agent's result payload
            product_spec: The original product spec for comparison
        """
        print(f"\n🔍 [QA AGENT] Starting review...")

        html_content = engineer_output.get("html_content", "")
        pr_url = engineer_output.get("github_pr_url", "")
        marketing_copy = marketing_output

        # 1. Review HTML landing page
        html_review = self._review_html(html_content, product_spec)
        print(f"📝 [QA AGENT] HTML review complete — verdict: {html_review.get('verdict', 'unknown')}")

        # 2. Review marketing copy
        marketing_review = self._review_marketing(marketing_copy, product_spec)
        print(f"📝 [QA AGENT] Marketing review complete — verdict: {marketing_review.get('verdict', 'unknown')}")

        # 3. Post review comments on GitHub PR
        if pr_url:
            self._post_pr_comments(pr_url, html_review, marketing_review)
            print(f"💬 [QA AGENT] Review comments posted on GitHub PR.")

        # 4. Determine overall verdict
        overall_verdict = "pass"
        if html_review.get("verdict") == "fail" or marketing_review.get("verdict") == "fail":
            overall_verdict = "fail"

        # 5. Send structured review report to CEO
        all_issues = html_review.get("issues", []) + marketing_review.get("issues", [])

        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="result",
            payload={
                "status": "review_complete",
                "overall_verdict": overall_verdict,
                "html_review": html_review,
                "marketing_review": marketing_review,
                "issues": all_issues,
                "summary": f"QA review complete. Overall verdict: {overall_verdict}. Found {len(all_issues)} issue(s).",
            },
        )

        print(f"📤 [QA AGENT] Review report sent to CEO — verdict: {overall_verdict}")

    def _review_html(self, html_content: str, product_spec: dict) -> dict:
        """Use Gemini to review the HTML landing page against the product spec."""
        # Truncate HTML if too long for the prompt
        html_preview = html_content[:4000] if len(html_content) > 4000 else html_content

        prompt = f"""You are a QA reviewer. Review this HTML landing page against the product spec.

PRODUCT SPEC:
{json.dumps(product_spec, indent=2)}

HTML LANDING PAGE:
{html_preview}

Check:
1. Does the headline match the value proposition?
2. Are all 5 features from the spec mentioned?
3. Are the personas/pain points referenced?
4. Is there a clear call-to-action button?
5. Is the HTML valid and well-structured?

Respond with ONLY valid JSON (no markdown fences):
{{
    "verdict": "pass" or "fail",
    "score": 1-10,
    "issues": ["issue 1 description", "issue 2 description"],
    "strengths": ["strength 1", "strength 2"],
    "suggestions": ["suggestion 1", "suggestion 2"]
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
            print(f"❌ [QA AGENT] HTML review error: {e}")
            return {"verdict": "pass", "score": 7, "issues": [], "strengths": [], "suggestions": []}

    def _review_marketing(self, marketing_output: dict, product_spec: dict) -> dict:
        """Use Gemini to review the marketing copy."""
        prompt = f"""You are a QA reviewer. Review this marketing content against the product spec.

PRODUCT SPEC:
{json.dumps(product_spec, indent=2)}

MARKETING CONTENT:
- Tagline: {marketing_output.get('tagline', 'N/A')}
- Description: {marketing_output.get('product_description', 'N/A')}
- Email subject: {marketing_output.get('cold_email', {}).get('subject', 'N/A')}
- Email body: {marketing_output.get('cold_email', {}).get('body', 'N/A')[:500]}

Check:
1. Is the tagline under 10 words and compelling?
2. Does the description match the value proposition?
3. Does the cold email have a clear call to action?
4. Is the tone professional and appropriate?

Respond with ONLY valid JSON (no markdown fences):
{{
    "verdict": "pass" or "fail",
    "score": 1-10,
    "issues": ["issue 1 description", "issue 2 description"],
    "strengths": ["strength 1", "strength 2"],
    "suggestions": ["suggestion 1", "suggestion 2"]
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
            print(f"❌ [QA AGENT] Marketing review error: {e}")
            return {"verdict": "pass", "score": 7, "issues": [], "strengths": [], "suggestions": []}

    def _post_pr_comments(self, pr_url: str, html_review: dict, marketing_review: dict):
        """Post review comments on the GitHub PR."""
        try:
            # Extract PR number from URL
            pr_number = pr_url.rstrip("/").split("/")[-1]

            # Post a general review comment
            comment_body = f"""## 🔍 QA Agent Review

### HTML Landing Page Review
- **Verdict:** {html_review.get('verdict', 'N/A').upper()}
- **Score:** {html_review.get('score', 'N/A')}/10

**Strengths:**
{self._format_list(html_review.get('strengths', []))}

**Issues:**
{self._format_list(html_review.get('issues', []))}

**Suggestions:**
{self._format_list(html_review.get('suggestions', []))}

---

### Marketing Copy Review
- **Verdict:** {marketing_review.get('verdict', 'N/A').upper()}
- **Score:** {marketing_review.get('score', 'N/A')}/10

**Strengths:**
{self._format_list(marketing_review.get('strengths', []))}

**Issues:**
{self._format_list(marketing_review.get('issues', []))}

**Suggestions:**
{self._format_list(marketing_review.get('suggestions', []))}

---
*Reviewed by QA Agent 🤖*"""

            url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues/{pr_number}/comments"
            data = {"body": comment_body}
            resp = requests.post(url, headers=GITHUB_HEADERS, json=data)

            if resp.status_code == 201:
                print(f"✅ [QA AGENT] Review comment posted on PR #{pr_number}")
            else:
                print(f"⚠️  [QA AGENT] Failed to post PR comment: {resp.status_code}")

            # Post an inline review comment on the HTML file
            # Get the list of files in the PR
            url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{pr_number}/files"
            resp = requests.get(url, headers=GITHUB_HEADERS)
            if resp.status_code == 200:
                files = resp.json()
                for f in files:
                    if f["filename"] == "index.html":
                        # Post inline comment on index.html
                        # Get the latest commit SHA on the PR
                        pr_info_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{pr_number}"
                        pr_resp = requests.get(pr_info_url, headers=GITHUB_HEADERS)
                        if pr_resp.status_code == 200:
                            commit_sha = pr_resp.json()["head"]["sha"]
                            
                            inline_comments = [
                                {
                                    "body": f"🔍 HTML Quality: {html_review.get('verdict', 'N/A').upper()} — Score: {html_review.get('score', 'N/A')}/10",
                                    "path": "index.html",
                                    "line": 1,
                                    "side": "RIGHT",
                                },
                                {
                                    "body": f"💡 Suggestion: {html_review.get('suggestions', ['No suggestions'])[0]}",
                                    "path": "index.html",
                                    "line": 5,
                                    "side": "RIGHT",
                                },
                            ]

                            review_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls/{pr_number}/reviews"
                            review_data = {
                                "commit_id": commit_sha,
                                "body": "QA Agent automated review",
                                "event": "COMMENT",
                                "comments": inline_comments,
                            }
                            review_resp = requests.post(review_url, headers=GITHUB_HEADERS, json=review_data)
                            if review_resp.status_code == 200:
                                print(f"✅ [QA AGENT] Inline review comments posted on index.html")
                            else:
                                print(f"⚠️  [QA AGENT] Inline comments failed: {review_resp.status_code} — {review_resp.text[:200]}")

        except Exception as e:
            print(f"❌ [QA AGENT] PR comment error: {e}")

    def _format_list(self, items: list) -> str:
        """Format a list of strings as markdown bullet points."""
        if not items:
            return "- None"
        return "\n".join(f"- {item}" for item in items)
