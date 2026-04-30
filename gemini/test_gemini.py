import os
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Ensure your .env has GOOGLE_CLOUD_LOCATION=us-central1
client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION")
)

# EXACT MODEL ID for Vertex AI Gemini 3
MODEL_ID = "gemini-3.1-flash-lite-preview"

try:
    start = time.perf_counter()
    response = client.models.generate_content(
        model=MODEL_ID,
        contents="Hello, identify yourself."
    )
    elapsed_s = time.perf_counter() - start

    print(f"Model Output: {response.text}")
    print(f"Response time: {elapsed_s:.3f} s")

except Exception as e:
    print(f"Still failing? Error: {e}")
    # This loop will show you EXACTLY what names your project can see:
    print("\nListing available models for your credentials:")
    for model in client.models.list():
        print(f" - {model.name}")