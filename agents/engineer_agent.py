"""
LaunchMind GigGuard - Engineer Agent
Generates the landing page and takes real actions on GitHub.
"""

import base64
import json
import os

import requests
from dotenv import load_dotenv

from llm_helper import call_llm

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_REPO_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO_NAME")
GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "EngineerAgent <agent@launchmind.ai>",
}


class EngineerAgent:
    """The Engineer agent builds the HTML landing page and opens GitHub artifacts."""

    def __init__(self, message_bus):
        self.name = "engineer"
        self.bus = message_bus
        self.branch_name = "feature/landing-page"
        self.html_content = None
        self.last_product_spec = None
        self.last_task = None

    def run(self):
        """Receive the CEO task and product spec, then generate engineering outputs."""
        print("\n🔧 [ENGINEER AGENT] Starting...")
        task_msg, spec_msg = self._consume_inputs()

        if not task_msg:
            print("❌ [ENGINEER AGENT] No task received from CEO.")
            self._send_failure("No task received from CEO.", None)
            return
        if not spec_msg:
            print("❌ [ENGINEER AGENT] No product spec received.")
            self._send_failure("No product spec received.", task_msg["message_id"])
            return

        self.last_task = task_msg
        self.last_product_spec = spec_msg["payload"]["product_spec"]
        print("📋 [ENGINEER AGENT] Received task and product spec. Generating landing page...")

        result = self._execute_engineering_flow(
            product_spec=self.last_product_spec,
            focus=task_msg["payload"].get("focus", ""),
            parent_message_id=spec_msg["message_id"],
        )
        self._send_result(result, parent_message_id=spec_msg["message_id"])

    def handle_revision(self, revision_msg):
        """Regenerate the landing page after CEO feedback."""
        print("\n🔄 [ENGINEER AGENT] Received revision request...")
        product_spec = revision_msg["payload"].get("product_spec") or self.last_product_spec
        if not product_spec:
            self._send_failure("Cannot revise without a product spec.", revision_msg["message_id"])
            return

        instruction = revision_msg["payload"].get("instruction", "")
        issues = revision_msg["payload"].get("issue", "")
        self.last_product_spec = product_spec
        revision_context = f"QA issues: {issues}\nCEO instruction: {instruction}"
        self.html_content = self._generate_landing_page(
            product_spec=product_spec,
            focus=self.last_task["payload"].get("focus", "") if self.last_task else "",
            revision_context=revision_context,
        )
        if not self.html_content:
            self._send_failure("Failed to regenerate landing page during revision.", revision_msg["message_id"])
            return

        commit_success = self._commit_to_branch(commit_message="fix: revise GigGuard landing page")
        if not commit_success:
            self._send_failure("Failed to recommit revised landing page to GitHub.", revision_msg["message_id"])
            return

        existing_pr_url = revision_msg["payload"].get("github_pr_url") or self._find_existing_pull_request_url()
        existing_issue_url = revision_msg["payload"].get("github_issue_url") or self._find_existing_issue_url()
        result = {
            "status": "completed",
            "github_issue_url": existing_issue_url or "",
            "github_pr_url": existing_pr_url or "",
            "branch_name": self.branch_name,
            "files_committed": ["index.html"],
            "summary": "Landing page revised and recommitted to the existing pull request.",
            "html_content": self.html_content,
        }
        self._send_result(result, parent_message_id=revision_msg["message_id"])

    def _consume_inputs(self):
        messages = self.bus.receive(self.name)
        task_msg = None
        spec_msg = None
        for msg in messages:
            if msg["message_type"] == "task":
                task_msg = msg
            elif msg["message_type"] == "result" and "product_spec" in msg.get("payload", {}):
                spec_msg = msg
        return task_msg, spec_msg

    def _execute_engineering_flow(
        self,
        product_spec: dict,
        focus: str,
        parent_message_id: str,
        revision_context: str = "",
    ) -> dict:
        self.html_content = self._generate_landing_page(product_spec, focus, revision_context)
        if not self.html_content:
            return self._failure_payload("Failed to generate landing page.", parent_message_id)

        issue_url = self._create_github_issue(product_spec, focus, revision_context)
        if not issue_url:
            return self._failure_payload("Failed to create GitHub issue.", parent_message_id)

        commit_success = self._commit_to_branch()
        if not commit_success:
            return self._failure_payload("Failed to commit landing page to GitHub.", parent_message_id)

        pr_url = self._open_pull_request(product_spec, revision_context)
        if not pr_url:
            return self._failure_payload("Failed to open GitHub pull request.", parent_message_id)

        return {
            "status": "completed",
            "github_issue_url": issue_url,
            "github_pr_url": pr_url,
            "branch_name": self.branch_name,
            "files_committed": ["index.html"],
            "summary": "Landing page created, committed, and submitted as a pull request.",
            "html_content": self.html_content,
        }

    def _generate_landing_page(self, product_spec: dict, focus: str, revision_context: str = "") -> str:
        prompt = f"""You are an expert frontend developer. Generate a complete, working HTML landing page for GigGuard.

PRODUCT SPEC:
{json.dumps(product_spec, indent=2)}

CEO ENGINEERING FOCUS:
{focus}

REVISION CONTEXT:
{revision_context or "None"}

Requirements:
- Single HTML file with all CSS embedded in a <style> tag
- Include a headline, subheadline, features section, CTA button, and basic CSS styling
- Mention all 5 features from the product spec
- Include the personas or their pain points in the page
- Responsive layout that works on mobile
- CTA button text should be "Start Free Trial"

Return ONLY raw HTML."""
        html = call_llm(prompt, agent_name=self.name)
        return self._clean_html_output(html)

    def _create_github_issue(self, product_spec: dict, focus: str, revision_context: str = "") -> str:
        prompt = f"""Write a GitHub issue description for creating the GigGuard landing page.

Value proposition: {product_spec.get("value_proposition", "")}
Features: {json.dumps(product_spec.get("features", []), indent=2)}
Focus: {focus}
Revision context: {revision_context or "None"}

Write 3-4 short sentences. Return ONLY the description text."""
        description = call_llm(prompt, agent_name=self.name)
        if not description:
            return None

        url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
        data = {
            "title": "Initial landing page",
            "body": description.strip(),
            "labels": ["enhancement"],
        }
        resp = requests.post(url, headers=GITHUB_HEADERS, json=data, timeout=30)
        if resp.status_code == 201:
            return resp.json().get("html_url", "")

        print(f"⚠️  [ENGINEER AGENT] GitHub issue creation failed: {resp.status_code} - {resp.text}")
        return None

    def _commit_to_branch(self, commit_message: str = "feat: add GigGuard landing page") -> bool:
        try:
            ref_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs/heads/main"
            ref_resp = requests.get(ref_url, headers=GITHUB_HEADERS, timeout=30)
            if ref_resp.status_code != 200:
                print(f"⚠️  [ENGINEER AGENT] Could not get main branch ref: {ref_resp.status_code} - {ref_resp.text}")
                return False

            main_sha = ref_resp.json()["object"]["sha"]
            branch_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs"
            branch_resp = requests.post(
                branch_url,
                headers=GITHUB_HEADERS,
                json={"ref": f"refs/heads/{self.branch_name}", "sha": main_sha},
                timeout=30,
            )
            if branch_resp.status_code not in (201, 422):
                print(f"⚠️  [ENGINEER AGENT] Branch creation failed: {branch_resp.status_code} - {branch_resp.text}")
                return False

            content_b64 = base64.b64encode(self.html_content.encode("utf-8")).decode()
            contents_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/index.html"
            existing_resp = requests.get(
                contents_url,
                headers=GITHUB_HEADERS,
                params={"ref": self.branch_name},
                timeout=30,
            )
            data = {
                "message": commit_message,
                "content": content_b64,
                "branch": self.branch_name,
                "committer": {
                    "name": "EngineerAgent",
                    "email": "agent@launchmind.ai",
                },
            }
            if existing_resp.status_code == 200:
                data["sha"] = existing_resp.json()["sha"]

            put_resp = requests.put(contents_url, headers=GITHUB_HEADERS, json=data, timeout=30)
            if put_resp.status_code in (200, 201):
                return True

            print(f"⚠️  [ENGINEER AGENT] Commit failed: {put_resp.status_code} - {put_resp.text}")
            return False
        except Exception as exc:
            print(f"❌ [ENGINEER AGENT] Commit error: {exc}")
            return False

    def _open_pull_request(self, product_spec: dict, revision_context: str = "") -> str:
        prompt = f"""Write a pull request description for the GigGuard landing page.

Value proposition: {product_spec.get("value_proposition", "")}
Feature names: {json.dumps([feature.get("name") for feature in product_spec.get("features", [])], indent=2)}
Revision context: {revision_context or "None"}

Include what was added, why, and a short checklist. Return ONLY the PR body text."""
        pr_body = call_llm(prompt, agent_name=self.name)
        if not pr_body:
            return None

        url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls"
        data = {
            "title": "feat: GigGuard landing page - generated by Engineer Agent",
            "body": pr_body.strip(),
            "head": self.branch_name,
            "base": "main",
        }
        resp = requests.post(url, headers=GITHUB_HEADERS, json=data, timeout=30)
        if resp.status_code == 201:
            return resp.json().get("html_url", "")
        if resp.status_code == 422 and "A pull request already exists" in resp.text:
            pulls_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls"
            pulls_resp = requests.get(
                pulls_url,
                headers=GITHUB_HEADERS,
                params={"state": "open", "head": f"{GITHUB_OWNER}:{self.branch_name}"},
                timeout=30,
            )
            if pulls_resp.status_code == 200 and pulls_resp.json():
                return pulls_resp.json()[0].get("html_url", "")

        print(f"⚠️  [ENGINEER AGENT] PR creation failed: {resp.status_code} - {resp.text}")
        return None

    def _find_existing_pull_request_url(self) -> str | None:
        try:
            pulls_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls"
            pulls_resp = requests.get(
                pulls_url,
                headers=GITHUB_HEADERS,
                params={"state": "open", "head": f"{GITHUB_OWNER}:{self.branch_name}"},
                timeout=30,
            )
            if pulls_resp.status_code == 200 and pulls_resp.json():
                return pulls_resp.json()[0].get("html_url", "")
        except Exception as exc:
            print(f"⚠️  [ENGINEER AGENT] Could not find existing PR URL: {exc}")
        return None

    def _find_existing_issue_url(self) -> str | None:
        try:
            issues_url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
            issues_resp = requests.get(
                issues_url,
                headers=GITHUB_HEADERS,
                params={"state": "open"},
                timeout=30,
            )
            if issues_resp.status_code == 200:
                for issue in issues_resp.json():
                    if issue.get("title") == "Initial landing page":
                        return issue.get("html_url", "")
        except Exception as exc:
            print(f"⚠️  [ENGINEER AGENT] Could not find existing issue URL: {exc}")
        return None

    def _clean_html_output(self, html: str | None) -> str | None:
        if not html:
            return html
        cleaned = html.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        if cleaned.lower().startswith("html"):
            cleaned = cleaned[4:]
        return cleaned.strip()

    def _failure_payload(self, reason: str, parent_message_id: str) -> dict:
        return {
            "status": "failed",
            "error": reason,
            "github_issue_url": "",
            "github_pr_url": "",
            "branch_name": self.branch_name,
            "files_committed": [],
            "summary": reason,
            "html_content": self.html_content or "",
            "parent_message_id": parent_message_id,
        }

    def _send_failure(self, reason: str, parent_message_id: str | None):
        self._send_result(self._failure_payload(reason, parent_message_id or ""))

    def _send_result(self, payload: dict, parent_message_id: str | None = None):
        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="result",
            payload=payload,
            parent_message_id=parent_message_id,
        )
        if payload.get("status") == "completed":
            print("📤 [ENGINEER AGENT] Results sent to CEO.")
        else:
            print(f"❌ [ENGINEER AGENT] {payload.get('summary', 'Engineering failed.')}")
