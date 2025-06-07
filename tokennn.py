import os
from flask import Flask, request, redirect
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)

# SET THESE with your actual credentials
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "your-client-id")
SPOTIFY_SECRET = os.environ.get("SPOTIFY_SECRET", "your-client-secret")
SPOTIFY_REDIRECT_URI = "http://localhost:8888/callback"

SCOPE = "user-read-playback-state user-modify-playback-state"

auth_manager = SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SCOPE
)

@app.route("/")
def index():
    auth_url = auth_manager.get_authorize_url()
    return f"""
    <h1>Spotify Auth</h1>
    <p><a href="{auth_url}">Click here to authorize</a></p>
    """

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "No code provided in the callback."

    token_info = auth_manager.get_access_token(code, as_dict=True)

    access_token = token_info["access_token"]
    refresh_token = token_info["refresh_token"]
    expires_in = token_info["expires_in"]

    return f"""
    <h1>✅ Authorized!</h1>
    <p><b>Access Token:</b> {access_token}</p>
    <p><b>Refresh Token:</b> {refresh_token}</p>
    <p><b>Expires In:</b> {expires_in} seconds</p>
    <p><i>Copy this refresh token and set it in your Render env as SPOTIFY_REFRESH_TOKEN.</i></p>
    """

if __name__ == "__main__":
    app.run(port=8888, debug=True)
