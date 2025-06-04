import os

# Loads env vars automatically if you call load_dotenv() in main.py
SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_SECRET        = os.getenv("SPOTIFY_SECRET")
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI")
UBER_SERVER_TOKEN     = os.getenv("UBER_SERVER_TOKEN")
GEMINI_API_KEY        = os.getenv("GEMINI_API_KEY")
PERSONALITY_PROMPT    = os.getenv("PERSONALITY_PROMPT", "You are a helpful assistant.")
CONTACTS_FILE         = os.getenv("CONTACTS_FILE", "contacts.json")
DAILY_EMAIL_TO        = os.getenv("DAILY_EMAIL_TO")
