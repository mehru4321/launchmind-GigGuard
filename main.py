"""
LaunchMind GigGuard - Main Entry Point
Runs the multi-agent system end-to-end.
"""

import io
import os
import sys

from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

REQUIRED_VARS = [
    "GEMINI_API_KEY",
    "GITHUB_TOKEN",
    "GITHUB_REPO_OWNER",
    "GITHUB_REPO_NAME",
    "SLACK_BOT_TOKEN",
]

EMAIL_PROVIDER = (os.getenv("EMAIL_PROVIDER") or "brevo").strip().lower()
EMAIL_REQUIRED_VARS = {
    "brevo": ["BREVO_API_KEY", "BREVO_FROM_EMAIL", "BREVO_TO_EMAIL"],
    "sendgrid": ["SENDGRID_API_KEY", "SENDGRID_FROM_EMAIL", "SENDGRID_TO_EMAIL"],
}

missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if EMAIL_PROVIDER not in EMAIL_REQUIRED_VARS:
    missing.append("EMAIL_PROVIDER must be one of: brevo, sendgrid")
else:
    missing.extend([var for var in EMAIL_REQUIRED_VARS[EMAIL_PROVIDER] if not os.getenv(var)])

if missing:
    print(f"❌ Missing environment variables: {', '.join(missing)}")
    print("   Copy .env.example to .env and fill in the required API keys and settings.")
    sys.exit(1)

from agents.ceo_agent import CEOAgent
from message_bus import MessageBus

STARTUP_IDEA = (
    "GigGuard - a freelancer toolkit that helps independent workers track project deadlines, "
    "manage unpaid invoices, and auto-send polite payment reminders to clients. "
    "Target users are freelance designers, developers, and writers who juggle multiple clients "
    "and lose track of who owes them money. GigGuard gives them a single dashboard to see "
    "all invoices (sent, viewed, paid, overdue), a deadline calendar, and automated follow-up "
    "emails so they never have to write awkward payment reminders themselves."
)


def main():
    """Run the full LaunchMind GigGuard multi-agent system."""
    print("=" * 60)
    print("  🚀 LaunchMind GigGuard - Multi-Agent System")
    print("  📅 Starting full pipeline...")
    print("=" * 60)

    bus = MessageBus()
    ceo = CEOAgent(bus)
    result = ceo.run(STARTUP_IDEA)

    print("\n" + "=" * 60)
    if result.get("status") == "completed":
        print("  ✅ PIPELINE COMPLETE")
    else:
        print("  ❌ PIPELINE FAILED")
    print("=" * 60)
    print(f"  Status:     {result.get('status', 'failed')}")
    print(f"  PR URL:     {result.get('pr_url', 'N/A') or 'N/A'}")
    print(f"  Issue URL:  {result.get('issue_url', 'N/A') or 'N/A'}")
    print(f"  QA Verdict: {result.get('qa_verdict', 'N/A')}")
    if result.get("error"):
        print(f"  Error:      {result['error']}")
    print("=" * 60)

    bus.print_full_history()
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
