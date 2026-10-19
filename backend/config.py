"""
Configuration for CoachGPT. Everything environment-specific is read here,
from the .env file (or real environment variables), so no key or setting
is ever hardcoded in the source.

LLM_PROVIDER:
  gemini -> real AI via Google Gemini (free tier available)
  mock   -> no AI, no key; answers come from the built-in datasets
"""

import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "mock").lower()
API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

client = None
if API_KEY:
    # Imported lazily so mock mode works even without the package installed.
    from google import genai
    client = genai.Client(api_key=API_KEY)

if LLM_PROVIDER == "gemini" and not API_KEY:
    print("WARNING: LLM_PROVIDER=gemini but GEMINI_API_KEY is not set.")
