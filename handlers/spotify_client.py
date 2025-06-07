import os
import logging
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import session

logger = logging.getLogger(__name__)

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
    
    # If no token info in session, try environment refresh token
    if not token_info:
        refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        if refresh_token:
            logger.info("No session token, trying environment refresh token...")
            try:
                sp_oauth = make_spotify_oauth()
                # Fix deprecation warning by using as_dict=True
                token_info = sp_oauth.refresh_access_token(refresh_token, as_dict=True)
                session["token_info"] = token_info
                logger.info("Successfully refreshed token from environment")
                return token_info
            except Exception as e:
                logger.error(f"Error refreshing token from environment: {e}")
                # Clear invalid refresh token from environment (in production, you'd want to handle this differently)
                return None
        return None
    
    # Check if current token is expired
    sp_oauth = make_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        logger.info("Session token expired, attempting refresh...")
        try:
            # Fix deprecation warning by using as_dict=True
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"], as_dict=True)
            session["token_info"] = token_info
            logger.info("Successfully refreshed session token")
        except Exception as e:
            logger.error(f"Error refreshing session token: {e}")
            # Clear invalid token from session
            session.pop("token_info", None)
            return None
    
    return token_info

def get_spotify_client():
    """Get authenticated Spotify client"""
    token_info = get_token_info()
    if not token_info:
        logger.warning("No valid Spotify token available")
        return None
    
    try:
        return spotipy.Spotify(auth=token_info["access_token"])
    except Exception as e:
        logger.error(f"Error creating Spotify client: {e}")
        return None

def clear_invalid_tokens():
    """Clear invalid tokens from session"""
    session.pop("token_info", None)
    logger.info("Cleared invalid tokens from session")