"""
LaunchMind GigGuard — Marketing Agent
Generates marketing content, sends real email via SendGrid, and posts to Slack.
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
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")
SENDGRID_TO_EMAIL = os.getenv("SENDGRID_TO_EMAIL")


class MarketingAgent:
    """
    The Marketing agent thinks like a growth marketer.
    It generates tagline, description, cold email, social posts,
    then sends a real email via SendGrid and posts to Slack.
    """

    def __init__(self, message_bus):
        self.name = "marketing"
        self.bus = message_bus
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.slack_client = WebClient(token=SLACK_BOT_TOKEN)

    def run(self, pr_url: str = None):
        """Main execution: receive spec, generate copy, send email, post Slack."""
        print(f"\n📣 [MARKETING AGENT] Starting...")

        # 1. Receive product spec from Product agent
        messages = self.bus.receive(self.name)
        spec_msg = None
        for m in messages:
            if m["message_type"] == "result" and "product_spec" in m.get("payload", {}):
                spec_msg = m
                break

        if not spec_msg:
            print("❌ [MARKETING AGENT] No product spec received.")
            return

        product_spec = spec_msg["payload"]["product_spec"]
        print("📋 [MARKETING AGENT] Received product spec. Generating marketing content...")

        # 2. Generate all marketing content using LLM
        marketing_content = self._generate_marketing_content(product_spec)
        if not marketing_content:
            print("❌ [MARKETING AGENT] Failed to generate marketing content.")
            return

        print("✅ [MARKETING AGENT] Marketing content generated.")

        # 3. Send real email via SendGrid
        email_sent = self._send_email(marketing_content)

        # 4. Post to Slack #launches channel
        slack_posted = self._post_to_slack(marketing_content, pr_url)

        # 5. Send all copy back to CEO
        self.bus.send(
            from_agent=self.name,
            to_agent="ceo",
            message_type="result",
            payload={
                "status": "completed",
                "tagline": marketing_content.get("tagline", ""),
                "product_description": marketing_content.get("product_description", ""),
                "cold_email": {
                    "subject": marketing_content.get("email_subject", ""),
                    "body": marketing_content.get("email_body", ""),
                    "sent_to": SENDGRID_TO_EMAIL or "not configured",
                    "sent": email_sent,
                },
                "social_posts": {
                    "twitter": marketing_content.get("twitter_post", ""),
                    "linkedin": marketing_content.get("linkedin_post", ""),
                    "instagram": marketing_content.get("instagram_post", ""),
                },
                "slack_message_posted": slack_posted,
                "slack_channel": "#launches",
            },
            parent_message_id=spec_msg["message_id"],
        )

        print("📤 [MARKETING AGENT] Results sent to CEO.")

    def _generate_marketing_content(self, product_spec: dict) -> dict:
        """Use Gemini to generate all marketing content."""
        prompt = f"""You are an expert growth marketer. Generate marketing content for GigGuard.

PRODUCT SPEC:
{json.dumps(product_spec, indent=2)}

Respond with ONLY valid JSON (no markdown fences, no extra text) in this exact format:
{{
    "tagline": "Under 10 words — punchy and memorable",
    "product_description": "2-3 sentences for a landing page. Clear and compelling.",
    "email_subject": "Compelling email subject line for cold outreach",
    "email_body": "A professional cold outreach email (3-4 paragraphs) to a potential early user or investor. Include a clear call to action at the end.",
    "twitter_post": "Twitter/X post under 280 characters with relevant hashtags and emoji",
    "linkedin_post": "Professional LinkedIn post (3-4 sentences) about the product launch",
    "instagram_post": "Instagram caption with emoji and hashtags"
}}

Make everything specific to GigGuard and freelancers. Be compelling and authentic."""

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
            print(f"❌ [MARKETING AGENT] LLM error: {e}")
            return None

    def _send_email(self, content: dict) -> bool:
        """Send a real email via SendGrid."""
        if not SENDGRID_API_KEY or SENDGRID_API_KEY.startswith("your-"):
            print("⚠️  [MARKETING AGENT] SendGrid not configured — skipping email send.")
            return False

        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail

            message = Mail(
                from_email=SENDGRID_FROM_EMAIL,
                to_emails=SENDGRID_TO_EMAIL,
                subject=content.get("email_subject", "GigGuard — Get Paid on Time"),
                html_content=f"""
                <h2>{content.get('tagline', 'GigGuard')}</h2>
                <p>{content.get('email_body', '').replace(chr(10), '<br>')}</p>
                <br>
                <p><em>Sent by GigGuard Marketing Agent</em></p>
                """,
            )

            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)

            if response.status_code in [200, 201, 202]:
                print(f"✅ [MARKETING AGENT] Email sent to {SENDGRID_TO_EMAIL}")
                return True
            else:
                print(f"⚠️  [MARKETING AGENT] Email failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ [MARKETING AGENT] Email error: {e}")
            return False

    def _post_to_slack(self, content: dict, pr_url: str = None) -> bool:
        """Post a formatted message to Slack #launches using Block Kit."""
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
                {"type": "divider"},
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*📧 Email Campaign:*\nSent to test inbox",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*🐦 Social Posts:*\n3 drafts ready (Twitter, LinkedIn, Instagram)",
                        },
                    ],
                },
            ]

            if pr_url:
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🔗 Landing Page PR:* <{pr_url}|View on GitHub>",
                        },
                    }
                )

            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Posted by GigGuard Marketing Agent 🤖",
                        }
                    ],
                }
            )

            response = self.slack_client.chat_postMessage(
                channel="#launches",
                text=f"🚀 GigGuard Launch: {content.get('tagline', '')}",
                blocks=blocks,
            )

            if response["ok"]:
                print("✅ [MARKETING AGENT] Slack message posted to #launches")
                return True
            else:
                print(f"⚠️  [MARKETING AGENT] Slack post failed: {response.get('error')}")
                return False

        except SlackApiError as e:
            print(f"❌ [MARKETING AGENT] Slack error: {e.response['error']}")
            return False
        except Exception as e:
            print(f"❌ [MARKETING AGENT] Slack error: {e}")
            return False
