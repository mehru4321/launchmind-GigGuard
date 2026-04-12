import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load .env file
load_dotenv()

# Get token
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

client = WebClient(token=SLACK_BOT_TOKEN)

try:
    # 18. Test the bot by running a quick Python script that calls the Slack API chat.postMessage endpoint
    response = client.chat_postMessage(
        channel="#launches",
        text="🚀 GigGuard bot is working from .env!"
    )
    print("Message sent successfully!")
except SlackApiError as e:
    print(f"Error: {e.response['error']}")