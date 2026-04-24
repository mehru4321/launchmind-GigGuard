"""
LaunchMind GigGuard - Marketing Agent
Generates marketing content, sends real email, and posts to Slack.
"""

import json
import os

import requests
import sib_api_v3_sdk
from dotenv import load_dotenv
from sib_api_v3_sdk.rest import ApiException
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from llm_helper import call_llm_json

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
EMAIL_PROVIDER = (os.getenv("EMAIL_PROVIDER") or "brevo").strip().lower()
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")
SENDGRID_TO_EMAIL = os.getenv("SENDGRID_TO_EMAIL")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_FROM_EMAIL = os.getenv("BREVO_FROM_EMAIL")
BREVO_TO_EMAIL = os.getenv("BREVO_TO_EMAIL")


class MarketingAgent:
    """The Marketing agent generates copy, sends email, and posts to Slack."""

    def __init__(self, message_bus):
        self.name = "marketing"
        self.bus = message_bus
        self.slack_client = WebClient(token=SLACK_BOT_TOKEN)
        self.last_product_spec = None
        self.last_task = None

    def run(self, pr_url: str = None):
        """Receive the CEO task and product spec, then ship marketing outputs."""
        print("\n📣 [MARKETING AGENT] Starting...")
        task_msg, spec_msg = self._consume_inputs()

        if not task_msg:
            print("❌ [MARKETING AGENT] No task received from CEO.")
            self._send_result(self._failure_payload("No task received from CEO."), None)
            return
        if not spec_msg:
            print("❌ [MARKETING AGENT] No product spec received.")
            self._send_result(
                self._failure_payload("No product spec received."),
                task_msg["message_id"],
            )
            return
        if not pr_url:
            print("❌ [MARKETING AGENT] No PR URL received from CEO.")
            self._send_result(
                self._failure_payload("No PR URL received from CEO."),
                spec_msg["message_id"],
            )
            return

        self.last_task = task_msg
        self.last_product_spec = spec_msg["payload"]["product_spec"]
        print("📋 [MARKETING AGENT] Received task and product spec. Generating marketing content...")

        payload = self._execute_marketing_flow(
            product_spec=self.last_product_spec,
            focus=task_msg["payload"].get("focus", ""),
            pr_url=pr_url,
        )
        self._send_result(payload, spec_msg["message_id"])

    def handle_revision(self, revision_msg, pr_url: str):
        """Revise copy after QA/CEO feedback and resend the live artifacts."""
        print("\n🔄 [MARKETING AGENT] Received revision request...")
        product_spec = revision_msg["payload"].get("product_spec") or self.last_product_spec
        if not product_spec:
            self._send_result(
                self._failure_payload("Cannot revise without a product spec."),
                revision_msg["message_id"],
            )
            return

        instruction = revision_msg["payload"].get("instruction", "")
        issues = revision_msg["payload"].get("issue", "")
        payload = self._execute_marketing_flow(
            product_spec=product_spec,
            focus=self.last_task["payload"].get("focus", "") if self.last_task else "",
            pr_url=pr_url,
            revision_context=f"QA issues: {issues}\nCEO instruction: {instruction}",
        )
        self._send_result(payload, revision_msg["message_id"])

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

    def _execute_marketing_flow(
        self,
        product_spec: dict,
        focus: str,
        pr_url: str,
        revision_context: str = "",
    ) -> dict:
        marketing_content = self._generate_marketing_content(product_spec, focus, revision_context)
        if not self._is_valid_marketing_content(marketing_content):
            return self._failure_payload("Failed to generate valid marketing content.")

        email_sent = self._send_email(marketing_content)
        if not email_sent:
            return self._failure_payload(f"Failed to send outreach email via {EMAIL_PROVIDER}.")

        slack_posted = self._post_to_slack(marketing_content, pr_url)
        if not slack_posted:
            return self._failure_payload("Failed to post launch message to Slack.")

        return {
            "status": "completed",
            "tagline": marketing_content.get("tagline", ""),
            "product_description": marketing_content.get("product_description", ""),
            "cold_email": {
                "subject": marketing_content.get("email_subject", ""),
                "body": marketing_content.get("email_body", ""),
                "sent_to": self._email_recipient(),
                "sent": True,
            },
            "social_posts": {
                "twitter": marketing_content.get("twitter_post", ""),
                "linkedin": marketing_content.get("linkedin_post", ""),
                "instagram": marketing_content.get("instagram_post", ""),
            },
            "slack_message_posted": True,
            "slack_channel": "#launches",
            "pr_url": pr_url,
            "summary": "Marketing copy generated, email sent, and Slack launch post published.",
        }

    def _generate_marketing_content(self, product_spec: dict, focus: str, revision_context: str = "") -> dict:
        prompt = f"""You are an expert growth marketer. Generate marketing content for GigGuard.

PRODUCT SPEC:
{json.dumps(product_spec, indent=2)}

CEO MARKETING FOCUS:
{focus}

REVISION CONTEXT:
{revision_context or "None"}

Respond with ONLY valid JSON in this exact format:
{{
    "tagline": "Under 10 words",
    "product_description": "2-3 sentence description",
    "email_subject": "Cold outreach subject line",
    "email_body": "Cold outreach email with a clear CTA",
    "twitter_post": "Twitter/X draft",
    "linkedin_post": "LinkedIn draft",
    "instagram_post": "Instagram draft"
}}"""
        return call_llm_json(prompt, agent_name=self.name)

    def _send_email(self, content: dict) -> bool:
        if EMAIL_PROVIDER == "brevo":
            return self._send_email_via_brevo(content)
        if EMAIL_PROVIDER == "sendgrid":
            return self._send_email_via_sendgrid(content)
        print(f"❌ [MARKETING AGENT] Unsupported EMAIL_PROVIDER: {EMAIL_PROVIDER}")
        return False

    def _send_email_via_sendgrid(self, content: dict) -> bool:
        try:
            response = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": SENDGRID_TO_EMAIL}]}],
                    "from": {"email": SENDGRID_FROM_EMAIL, "name": "GigGuard Marketing Agent"},
                    "subject": content.get("email_subject", ""),
                    "content": [
                        {
                            "type": "text/plain",
                            "value": content.get("email_body", ""),
                        }
                    ],
                },
                timeout=30,
            )
            if response.status_code == 202:
                print(f"✅ [MARKETING AGENT] Email sent to {SENDGRID_TO_EMAIL}")
                return True

            print(f"❌ [MARKETING AGENT] SendGrid error: {response.status_code} - {response.text}")
            return False
        except Exception as exc:
            print(f"❌ [MARKETING AGENT] Email error: {exc}")
            return False

    def _send_email_via_brevo(self, content: dict) -> bool:
        try:
            configuration = sib_api_v3_sdk.Configuration()
            configuration.api_key["api-key"] = BREVO_API_KEY
            api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

            email_body_html = content.get("email_body", "").replace("\n", "<br>")
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                html_content=(
                    f"<html><body><h2>{content.get('tagline', 'GigGuard')}</h2>"
                    f"<p>{email_body_html}</p></body></html>"
                ),
                sender={"email": BREVO_FROM_EMAIL, "name": "GigGuard Marketing Agent"},
                subject=content.get("email_subject", ""),
                to=[{"email": BREVO_TO_EMAIL, "name": "Test Recipient"}],
            )
            response = api_instance.send_transac_email(send_smtp_email)
            print(f"✅ [MARKETING AGENT] Email sent to {BREVO_TO_EMAIL} (ID: {response.message_id})")
            return True
        except ApiException as exc:
            print(f"❌ [MARKETING AGENT] Brevo API error: {exc}")
            return False
        except Exception as exc:
            print(f"❌ [MARKETING AGENT] Email error: {exc}")
            return False

    def _post_to_slack(self, content: dict, pr_url: str) -> bool:
        try:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚀 GigGuard Launch Announcement",
                        "emoji": True,
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{content.get('tagline', 'GigGuard')}*\n\n{content.get('product_description', '')}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Email:*\nSent to test inbox via {EMAIL_PROVIDER.title()}"},
                        {"type": "mrkdwn", "text": "*Social:*\n3 drafts ready (Twitter, LinkedIn, Instagram)"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*GitHub PR:* <{pr_url}|View the landing page pull request>",
                    },
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "Posted by GigGuard Marketing Agent"}],
                },
            ]
            response = self.slack_client.chat_postMessage(
                channel="#launches",
                text=f"GigGuard Launch: {content.get('tagline', '')}",
                blocks=blocks,
            )
            if response["ok"]:
                print("✅ [MARKETING AGENT] Slack message posted to #launches")
                return True
            print(f"⚠️  [MARKETING AGENT] Slack post failed: {response.get('error')}")
            return False
        except SlackApiError as exc:
            print(f"❌ [MARKETING AGENT] Slack error: {exc.response['error']}")
            return False
        except Exception as exc:
            print(f"❌ [MARKETING AGENT] Slack error: {exc}")
            return False

    def _is_valid_marketing_content(self, content: dict) -> bool:
        if not isinstance(content, dict):
            return False
        required = [
            "tagline",
            "product_description",
            "email_subject",
            "email_body",
            "twitter_post",
            "linkedin_post",
            "instagram_post",
        ]
        return all(content.get(key) for key in required)

    def _failure_payload(self, reason: str) -> dict:
        return {
            "status": "failed",
            "error": reason,
            "tagline": "",
            "product_description": "",
            "cold_email": {
                "subject": "",
                "body": "",
                "sent_to": self._email_recipient(),
                "sent": False,
            },
            "social_posts": {
                "twitter": "",
                "linkedin": "",
                "instagram": "",
            },
            "slack_message_posted": False,
            "slack_channel": "#launches",
            "pr_url": "",
            "summary": reason,
        }

    def _email_recipient(self) -> str:
        if EMAIL_PROVIDER == "brevo":
            return BREVO_TO_EMAIL or ""
        if EMAIL_PROVIDER == "sendgrid":
            return SENDGRID_TO_EMAIL or ""
        return ""

    def _send_result(self, payload: dict, parent_message_id: str | None):
        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="result",
            payload=payload,
            parent_message_id=parent_message_id,
        )
        if payload.get("status") == "completed":
            print("📤 [MARKETING AGENT] Results sent to CEO.")
        else:
            print(f"❌ [MARKETING AGENT] {payload.get('summary', 'Marketing failed.')}")
