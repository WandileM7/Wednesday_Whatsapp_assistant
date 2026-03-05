import os

# Loads env vars automatically if you call load_dotenv() in main.py
SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_SECRET        = os.getenv("SPOTIFY_SECRET")
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI")
UBER_SERVER_TOKEN     = os.getenv("UBER_SERVER_TOKEN")

# AI Configuration - Bytez (175k+ models) replaces Gemini
# Get your API key at https://bytez.com/settings
BYTEZ_API_KEY         = os.getenv("BYTEZ_API_KEY")
GEMINI_API_KEY        = os.getenv("GEMINI_API_KEY")  # Legacy, kept for fallback

# Bytez Model Selection - customize which models to use
# See https://bytez.com/models for 175,000+ available models
BYTEZ_CHAT_MODEL      = os.getenv("BYTEZ_CHAT_MODEL", "Qwen/Qwen3-4B")  # Fast chat model
BYTEZ_CHAT_MODEL_LARGE = os.getenv("BYTEZ_CHAT_MODEL_LARGE", "microsoft/Phi-3-mini-4k-instruct")
BYTEZ_IMAGE_MODEL     = os.getenv("BYTEZ_IMAGE_MODEL", "dreamlike-art/dreamlike-photoreal-2.0")
BYTEZ_TTS_MODEL       = os.getenv("BYTEZ_TTS_MODEL", "suno/bark-small")  # Text-to-speech
BYTEZ_VISION_MODEL    = os.getenv("BYTEZ_VISION_MODEL", "google/gemma-3-4b-it")  # Image analysis

PERSONALITY_PROMPT    = os.getenv("PERSONALITY_PROMPT", "You are a helpful assistant.")
CONTACTS_FILE         = os.getenv("CONTACTS_FILE", "contacts.json")
DAILY_EMAIL_TO        = os.getenv("DAILY_EMAIL_TO")
