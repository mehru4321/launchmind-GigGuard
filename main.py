"""
LaunchMind GigGuard — Main Entry Point
Runs the entire multi-agent system end-to-end.

Usage:
    python main.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Validate required env vars
REQUIRED_VARS = ["GEMINI_API_KEY", "GITHUB_TOKEN", "SLACK_BOT_TOKEN"]
missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    print(f"❌ Missing environment variables: {', '.join(missing)}")
    print("   Copy .env.example to .env and fill in your API keys.")
    sys.exit(1)

from message_bus import MessageBus
from agents.ceo_agent import CEOAgent


# ═══════════════════════════════════════════════════════
# GigGuard Startup Idea
# ═══════════════════════════════════════════════════════
STARTUP_IDEA = (
    "GigGuard — a freelancer toolkit that helps independent workers track project deadlines, "
    "manage unpaid invoices, and auto-send polite payment reminders to clients. "
    "Target users are freelance designers, developers, and writers who juggle multiple clients "
    "and lose track of who owes them money. GigGuard gives them a single dashboard to see "
    "all invoices (sent, viewed, paid, overdue), a deadline calendar, and automated follow-up "
    "emails so they never have to write awkward payment reminders themselves."
)


def main():
    """Run the full LaunchMind GigGuard multi-agent system."""
    print("=" * 60)
    print("  🚀 LaunchMind GigGuard — Multi-Agent System")
    print("  📅 Starting full pipeline...")
    print("=" * 60)

    # Initialize the message bus
    bus = MessageBus()

    # Initialize and run the CEO agent (it orchestrates everything)
    ceo = CEOAgent(bus)
    result = ceo.run(STARTUP_IDEA)

    # Print final results
    print("\n" + "=" * 60)
    print("  ✅ PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  PR URL:     {result.get('pr_url', 'N/A')}")
    print(f"  Issue URL:  {result.get('issue_url', 'N/A')}")
    print(f"  QA Verdict: {result.get('qa_verdict', 'N/A')}")
    print("=" * 60)

    # Print full message history
    bus.print_full_history()


if __name__ == "__main__":
    main()
