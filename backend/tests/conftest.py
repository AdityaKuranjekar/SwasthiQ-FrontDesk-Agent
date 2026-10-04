import os

# Tests must never reach the live Gemini API, even when backend/.env holds a real key.
# An empty value is treated as "no key" by agent/llm.py, so the model is skipped.
# The live check is run only by scripts/live_agreement.py or a test marked `live`.
os.environ["GEMINI_API_KEY"] = ""
