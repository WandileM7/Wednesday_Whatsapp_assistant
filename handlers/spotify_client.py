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
    
    # If no token info in session, try environment refresh token (but only if it exists and looks valid)
    if not token_info:
        refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        if refresh_token and len(refresh_token) > 20:  # Basic validation
            logger.info("No session token, trying environment refresh token...")
            try:
                sp_oauth = make_spotify_oauth()
                token_info = sp_oauth.refresh_access_token(refresh_token)
                session["token_info"] = token_info
                logger.info("Successfully refreshed token from environment")
                return token_info
            except Exception as e:
                # Only log as warning since this is a fallback mechanism
                logger.warning(f"Environment refresh token failed (expected if old): {e}")
                return None
        else:
            logger.debug("No valid environment refresh token available")
        return None
    
    # Check if current token is expired
    sp_oauth = make_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        logger.info("Session token expired, attempting refresh...")
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
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
        logger.debug("No valid Spotify token available")  # Changed to debug level
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

def is_authenticated():
    """Quick check if user is authenticated with Spotify"""
    return get_token_info() is not None