# 🚀 LaunchMind — GigGuard

> **GigGuard** is a freelancer toolkit that helps independent workers track project deadlines, manage unpaid invoices, and auto-send polite payment reminders to clients. Target users are freelance designers, developers, and writers who juggle multiple clients and need a single dashboard to stay on top of payments.

This project is a **Multi-Agent System (MAS)** where 5 autonomous AI agents collaborate to define, build, and market the GigGuard startup — from product spec to landing page to real emails and Slack posts.

---

## 🏗️ Agent Architecture

```
                         ┌──────────────┐
                         │   CEO Agent  │
                         │ (Orchestrator)│
                         └──────┬───────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                  │
              ▼                 ▼                  ▼
     ┌────────────────┐  ┌────────────┐  ┌──────────────────┐
     │ Product Agent  │  │  Engineer  │  │ Marketing Agent  │
     │  (PM Spec)     │  │  (Builder) │  │   (Growth)       │
     └───────┬────────┘  └─────┬──────┘  └───────┬──────────┘
             │                 │                  │
             │     ┌───────────┴──────────┐       │
             └────►│      QA Agent        │◄──────┘
                   │   (Reviewer)         │
                   └──────────────────────┘
```

### Communication Flow
1. **CEO** receives startup idea → decomposes into tasks via LLM → sends `task` messages to **Product Agent**
2. **Product Agent** generates product spec → sends `result` to **Engineer** and **Marketing**
3. **CEO** reviews Product's output via LLM → sends `revision_request` if needed (feedback loop)
4. **Engineer** generates HTML landing page → creates GitHub issue → commits to branch → opens PR
5. **Marketing** generates copy → sends email via SendGrid → posts to Slack
6. **QA** reviews HTML and marketing copy → posts PR review comments → sends pass/fail verdict
7. **CEO** reviews QA verdict → posts final summary to Slack

All messages follow a structured JSON schema with: `message_id`, `from_agent`, `to_agent`, `message_type`, `payload`, `timestamp`, `parent_message_id`.

---

## 📋 Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/mehru4321/launchmind-GigGuard.git
cd launchmind-GigGuard
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Set Environment Variables
Copy the example file and fill in your API keys:
```bash
cp .env.example .env
```

Edit `.env` with your real keys:
```
GEMINI_API_KEY=your-gemini-api-key
GITHUB_TOKEN=your-github-personal-access-token
GITHUB_REPO_OWNER=mehru4321
GITHUB_REPO_NAME=launchmind-GigGuard
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SENDGRID_API_KEY=your-sendgrid-api-key
SENDGRID_FROM_EMAIL=your-verified-sender@example.com
SENDGRID_TO_EMAIL=test-recipient@example.com
```

### 4. Run the System
```bash
python main.py
```

This runs the entire pipeline end-to-end. All agent messages will print to the terminal in real time.

---

## 🌐 Platform Integrations

| Platform | Agent | Action |
|----------|-------|--------|
| **GitHub** | Engineer Agent | Creates issue, commits HTML to feature branch, opens pull request |
| **GitHub** | QA Agent | Posts review comments (including inline comments) on the PR |
| **Slack** | Marketing Agent | Posts launch announcement to `#launches` with Block Kit formatting |
| **Slack** | CEO Agent | Posts final pipeline summary to `#launches` |
| **SendGrid** | Marketing Agent | Sends cold outreach email to test inbox |
| **Gemini** | All Agents | LLM reasoning for content generation, reviews, and decision-making |

---

## 🔗 Links

- **Slack Workspace:** [Join LaunchMind GigGuard Slack](https://join.slack.com/t/launchmind-gigguard/shared_invite/zt-3veichfhc-E9ZCDJWfV9E9lvA1zAeP5w)
- **GitHub Repository:** [mehru4321/launchmind-GigGuard](https://github.com/mehru4321/launchmind-GigGuard)
- **GitHub PR (by Engineer Agent):** *(generated at runtime — see PR tab after running)*

---

## 📂 Repository Structure

```
launchmind-GigGuard/
├── agents/
│   ├── __init__.py
│   ├── ceo_agent.py          # Orchestrator — decomposes, reviews, decides
│   ├── product_agent.py      # Generates product spec (personas, features, stories)
│   ├── engineer_agent.py     # Builds landing page, pushes to GitHub
│   ├── marketing_agent.py    # Generates copy, sends email, posts Slack
│   └── qa_agent.py           # Reviews outputs, posts PR comments
├── main.py                   # Single entry point — runs everything
├── message_bus.py            # Shared messaging system (structured JSON)
├── requirements.txt          # Python dependencies
├── .env.example              # Template for environment variables
├── .gitignore                # Excludes .env from commits
└── README.md                 # This file
```

---

## 👥 Group Members

| Member | Agent Responsibility |
|--------|---------------------|
| *member1* | CEO Agent, Product Agent |
| *member2* | Engineer Agent, Marketing Agent, QA Agent |
