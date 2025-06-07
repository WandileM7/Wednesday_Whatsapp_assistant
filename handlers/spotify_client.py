import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import session
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Import Spotify client functions
from handlers.spotify_client import make_spotify_oauth, get_spotify_client
SPOTIFY_SCOPE = "user-read-playback-state user-modify-playback-state"

def make_spotify_oauth():
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope=SPOTIFY_SCOPE,
        cache_path=None
    )

def get_token_info():
    """Get token info from session and refresh if needed"""
    token_info = session.get("token_info", {})
    if not token_info:
        # Try to use refresh token from environment
        refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        if refresh_token:
            try:
                sp_oauth = make_spotify_oauth()
                token_info = sp_oauth.refresh_access_token(refresh_token)
                session["token_info"] = token_info
                return token_info
            except Exception as e:
                print(f"Error refreshing token: {e}")
                return None
        return None
    
    sp_oauth = make_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
        except Exception as e:
            print(f"Error refreshing token: {e}")
            return None
    return token_info

def get_spotify_client():
    """Get authenticated Spotify client"""
    token_info = get_token_info()
    if not token_info:
        return None
    return spotipy.Spotify(auth=token_info["access_token"])