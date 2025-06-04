import os
import pickle
from flask import Blueprint, redirect, request
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly"
]

auth_bp = Blueprint("auth", __name__)

def get_creds_path():
    return os.path.join("tokens", "token.pkl")

@auth_bp.route("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(
        "credentials.json",
        scopes=SCOPES,
        redirect_uri="http://localhost:5000/oauth2callback"
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    return redirect(auth_url)

@auth_bp.route("/oauth2callback")
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        "credentials.json",
        scopes=SCOPES,
        redirect_uri="http://localhost:5000/oauth2callback"
    )
    flow.fetch_token(authorization_response=request.url)

    creds = flow.credentials
    os.makedirs("tokens", exist_ok=True)
    with open(get_creds_path(), "wb") as token:
        pickle.dump(creds, token)

    return "Authorization complete. You can close this window."

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