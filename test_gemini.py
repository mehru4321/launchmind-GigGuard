import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
model = os.getenv("LLM_MODEL", "gemini-2.0-flash-lite")

client = genai.Client(api_key=api_key)

try:
    # response = client.models.generate_content(
    #     model=model,
    #     contents="Reply with exactly: Gemini test successful",
    # )
    # print("MODEL:", model)
    # print("RESPONSE:", response.text)
    for model in client.models.list():
        print("Model:", model.name)
        print("Supported methods:", model.supported_actions)
        print("-" * 40)

except Exception as e:
    print("ERROR:", e)

    