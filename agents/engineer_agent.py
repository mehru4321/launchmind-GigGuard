"""
LaunchMind GigGuard — Engineer Agent
Generates HTML landing page and takes real actions on GitHub (issue, commit, PR).
"""

import os
import json
import base64
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
    "User-Agent": "EngineerAgent <agent@launchmind.ai>",
}


class EngineerAgent:
    """
    The Engineer agent is the builder.
    It reads the product spec, generates an HTML landing page,
    and takes real actions on GitHub: create issue, commit code, open PR.
    """

    def __init__(self, message_bus):
        self.name = "engineer"
        self.bus = message_bus
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.branch_name = "feature/landing-page"
        self.html_content = None

    def run(self):
        """Main execution: receive spec, generate HTML, push to GitHub."""
        print(f"\n🔧 [ENGINEER AGENT] Starting...")

        # 1. Receive product spec from Product agent
        messages = self.bus.receive(self.name)
        spec_msg = None
        for m in messages:
            if m["message_type"] == "result" and "product_spec" in m.get("payload", {}):
                spec_msg = m
                break

        if not spec_msg:
            print("❌ [ENGINEER AGENT] No product spec received.")
            return

        product_spec = spec_msg["payload"]["product_spec"]
        print("📋 [ENGINEER AGENT] Received product spec. Generating landing page...")

        # 2. Generate HTML landing page using LLM
        self.html_content = self._generate_landing_page(product_spec)
        if not self.html_content:
            print("❌ [ENGINEER AGENT] Failed to generate landing page.")
            return
        print("✅ [ENGINEER AGENT] Landing page HTML generated.")

        # 3. Create GitHub issue
        issue_url = self._create_github_issue(product_spec)
        print(f"📌 [ENGINEER AGENT] GitHub issue created: {issue_url}")

        # 4. Create branch and commit HTML file
        commit_success = self._commit_to_branch()
        if commit_success:
            print(f"📦 [ENGINEER AGENT] Code committed to branch: {self.branch_name}")
        else:
            print("❌ [ENGINEER AGENT] Failed to commit code to GitHub.")

        # 5. Open pull request
        pr_url = self._open_pull_request(product_spec)
        print(f"🔀 [ENGINEER AGENT] Pull request opened: {pr_url}")

        # 6. Send results back to CEO
        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="result",
            payload={
                "status": "completed",
                "github_issue_url": issue_url or "failed",
                "github_pr_url": pr_url or "failed",
                "branch_name": self.branch_name,
                "files_committed": ["index.html"],
                "summary": "Landing page created with GigGuard branding, feature cards, hero section with CTA, and responsive CSS. PR opened.",
                "html_content": self.html_content,
            },
            parent_message_id=spec_msg["message_id"],
        )

        print("📤 [ENGINEER AGENT] Results sent to CEO.")

    def _generate_landing_page(self, product_spec: dict) -> str:
        """Use Gemini to generate a complete HTML landing page."""
        prompt = f"""You are an expert frontend developer. Generate a complete, modern, beautiful HTML landing page for a startup called GigGuard.

PRODUCT SPEC:
{json.dumps(product_spec, indent=2)}

Requirements:
- Single HTML file with all CSS embedded in a <style> tag
- Modern, professional design with a dark gradient background
- Hero section with headline (value proposition), subheadline, and a CTA button
- Features section showing all 5 features as cards with icons (use emoji as icons)
- Testimonials/personas section showing the 3 personas and their pain points
- Footer with copyright
- Responsive design that works on mobile
- Use Google Fonts (Inter or similar)
- Smooth color scheme: deep blues, purples, and accent greens
- Subtle animations on scroll/hover
- The CTA button text should be "Start Free Trial"

Return ONLY the raw HTML code, no markdown fences, no explanation."""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            # Clean markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            if text.startswith("html"):
                text = text[4:]
            return text.strip()
        except Exception as e:
            print(f"❌ [ENGINEER AGENT] LLM error: {e}")
            return None

    def _create_github_issue(self, product_spec: dict) -> str:
        """Create a GitHub issue for the landing page task."""
        try:
            # Generate issue description with LLM
            prompt = f"""Write a GitHub issue description for creating a landing page for GigGuard.
The product has these features: {json.dumps(product_spec.get('features', []), indent=2)}
Value proposition: {product_spec.get('value_proposition', '')}

Write 3-4 sentences. Return ONLY the description text, no markdown fences."""

            response = self.model.generate_content(prompt)
            description = response.text.strip()

            # Create the issue via GitHub API
            url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
            data = {
                "title": "Initial landing page",
                "body": description,
                "labels": ["enhancement"],
            }
            resp = requests.post(url, headers=GITHUB_HEADERS, json=data)
            if resp.status_code == 201:
                return resp.json().get("html_url", "")
            else:
                print(f"⚠️  GitHub issue creation failed: {resp.status_code} — {resp.text}")
                return None
        except Exception as e:
            print(f"❌ [ENGINEER AGENT] Issue creation error: {e}")
            return None

    def _commit_to_branch(self) -> bool:
        """Create a new branch and commit the HTML file."""
        try:
            # 1. Get the SHA of the main branch
            url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs/heads/main"
            resp = requests.get(url, headers=GITHUB_HEADERS)
            if resp.status_code != 200:
                print(f"⚠️  Could not get main branch ref: {resp.status_code} — {resp.text}")
                return False
            main_sha = resp.json()["object"]["sha"]

            # 2. Create a new branch
            url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs"
            data = {
                "ref": f"refs/heads/{self.branch_name}",
                "sha": main_sha,
            }
            resp = requests.post(url, headers=GITHUB_HEADERS, json=data)
            if resp.status_code not in [201, 422]:  # 422 = branch already exists
                print(f"⚠️  Branch creation failed: {resp.status_code} — {resp.text}")
                return False

            # 3. Commit the HTML file
            content_b64 = base64.b64encode(self.html_content.encode()).decode()
            url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/index.html"

            # Check if file already exists on this branch
            resp = requests.get(url, headers=GITHUB_HEADERS, params={"ref": self.branch_name})
            data = {
                "message": "feat: add GigGuard landing page\n\nGenerated by Engineer Agent — includes hero section, features, personas, and CTA.",
                "content": content_b64,
                "branch": self.branch_name,
                "committer": {
                    "name": "EngineerAgent",
                    "email": "agent@launchmind.ai",
                },
            }
            if resp.status_code == 200:
                # File exists — update it
                data["sha"] = resp.json()["sha"]

            resp = requests.put(url, headers=GITHUB_HEADERS, json=data)
            if resp.status_code in [200, 201]:
                return True
            else:
                print(f"⚠️  Commit failed: {resp.status_code} — {resp.text}")
                return False

        except Exception as e:
            print(f"❌ [ENGINEER AGENT] Commit error: {e}")
            return False

    def _open_pull_request(self, product_spec: dict) -> str:
        """Open a pull request on GitHub."""
        try:
            # Generate PR description with LLM
            prompt = f"""Write a pull request description for the GigGuard landing page.
Value proposition: {product_spec.get('value_proposition', '')}
Features: {json.dumps([f['name'] for f in product_spec.get('features', [])], indent=2)}

Include: what was added, why, and a short checklist. Return ONLY the PR body text, no markdown fences."""

            response = self.model.generate_content(prompt)
            pr_body = response.text.strip()

            url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pulls"
            data = {
                "title": "feat: GigGuard landing page — generated by Engineer Agent",
                "body": pr_body,
                "head": self.branch_name,
                "base": "main",
            }
            resp = requests.post(url, headers=GITHUB_HEADERS, json=data)
            if resp.status_code == 201:
                return resp.json().get("html_url", "")
            else:
                print(f"⚠️  PR creation failed: {resp.status_code} — {resp.text}")
                return None
        except Exception as e:
            print(f"❌ [ENGINEER AGENT] PR error: {e}")
            return None
