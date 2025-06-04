import os
import pickle
from flask import Blueprint, redirect, request
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

auth_bp = Blueprint("auth", __name__)

# Google OAuth scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly"
]

# Get path to the pickle file where we store credentials
def get_creds_path():
    os.makedirs("tokens", exist_ok=True)
    return os.path.join("tokens", "token.pkl")

# Load credentials from token.pkl or refresh if expired
def load_credentials():
    creds = None
    token_path = get_creds_path()
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return creds

# /authorize: Starts the OAuth2 flow
@auth_bp.route("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json"),
        scopes=SCOPES,
        redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "https://waha-gemini-assistant.onrender.com/oauth2callback")
        
    )
    auth_url, _ = flow.authorization_url(prompt="consent", include_granted_scopes="true")
    return redirect(auth_url)

# /oauth2callback: Handles the OAuth2 callback and saves token
@auth_bp.route("/oauth2callback")
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json"),
        scopes=SCOPES,
        redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "https://waha-gemini-assistant.onrender.com/oauth2callback")
        
    )
    flow.fetch_token(authorization_response=request.url)

    creds = flow.credentials
    with open(get_creds_path(), "wb") as token:
        pickle.dump(creds, token)

    return "✅ Authorization complete. You can close this window."

