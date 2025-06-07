import os
import logging
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import session

logger = logging.getLogger(__name__)

def get_spotify_client():
    """Get authenticated Spotify client using session token"""
    try:
        # Get token from session (same as main.py)
        token_info = session.get("token_info")
        if not token_info:
            logger.warning("No Spotify token found in session")
            return None
        
        # Check if token is expired
        sp_oauth = SpotifyOAuth(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_SECRET"),
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
            scope="user-read-playback-state user-modify-playback-state",
            cache_path=None
        )
        
        if sp_oauth.is_token_expired(token_info):
            logger.info("Token expired, attempting refresh...")
            try:
                token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
                session["token_info"] = token_info
                logger.info("Token refreshed successfully")
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
                session.pop("token_info", None)
                return None
        
        return spotipy.Spotify(auth=token_info["access_token"])
        
    except Exception as e:
        logger.error(f"Error creating Spotify client: {e}")
        return None

def play_song(song_name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please visit /login to authenticate with Spotify."
    try:
        results = sp.search(q=song_name, type="track", limit=1)
        items = results["tracks"]["items"]
        if not items:
            return f"❌ Couldn't find '{song_name}'. Try a different search term."
        uri = items[0]["uri"]
        sp.start_playback(uris=[uri])
        return f"🎵 Now playing: {items[0]['name']} by {items[0]['artists'][0]['name']}"
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return "❌ Spotify authentication expired. Please visit /login to re-authenticate."
        elif e.http_status == 403:
            return "❌ Spotify Premium required for playback control."
        elif e.http_status == 404:
            return "❌ No active Spotify device found. Please open Spotify on a device first."
        else:
            logger.error(f"Spotify API error: {e}")
            return f"❌ Spotify error: {e}"
    except Exception as e:
        logger.error(f"Error playing song: {e}")
        return f"❌ Error playing song: {e}"

def get_current_song() -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please visit /login to authenticate with Spotify."
    try:
        playback = sp.current_playback()
        if not playback or not playback.get("item"):
            return "🔇 Nothing is playing right now."
        item = playback["item"]
        artist = item['artists'][0]['name'] if item.get('artists') else 'Unknown Artist'
        is_playing = playback.get('is_playing', False)
        status = "🎵 Playing" if is_playing else "⏸️ Paused"
        return f"{status}: {item['name']} by {artist}"
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return "❌ Spotify authentication expired. Please visit /login to re-authenticate."
        else:
            logger.error(f"Spotify API error: {e}")
            return f"❌ Spotify error: {e}"
    except Exception as e:
        logger.error(f"Error getting current song: {e}")
        return f"❌ Error getting current song: {e}"

def play_playlist(name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please visit /login to authenticate with Spotify."
    try:
        playlists = sp.current_user_playlists()["items"]
        for pl in playlists:
            if name.lower() in pl["name"].lower():
                sp.start_playbook(context_uri=pl["uri"])
                return f"🎵 Now playing playlist: {pl['name']}"
        
        # If not found in user playlists, search public playlists
        search_results = sp.search(q=name, type="playlist", limit=5)
        playlists = search_results["playlists"]["items"]
        for pl in playlists:
            if name.lower() in pl["name"].lower():
                sp.start_playback(context_uri=pl["uri"])
                return f"🎵 Now playing playlist: {pl['name']} by {pl['owner']['display_name']}"
        
        return f"❌ Couldn't find playlist named '{name}'. Try a different name."
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return "❌ Spotify authentication expired. Please visit /login to re-authenticate."
        elif e.http_status == 403:
            return "❌ Spotify Premium required for playback control."
        elif e.http_status == 404:
            return "❌ No active Spotify device found. Please open Spotify on a device first."
        else:
            logger.error(f"Spotify API error: {e}")
            return f"❌ Spotify error: {e}"
    except Exception as e:
        logger.error(f"Error playing playlist: {e}")
        return f"❌ Error playing playlist: {e}"

def play_album(name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please visit /login to authenticate with Spotify."
    try:
        items = sp.search(q=name, type="album", limit=1)["albums"]["items"]
        if not items:
            return f"❌ Couldn't find album '{name}'. Try a different search term."
        sp.start_playback(context_uri=items[0]["uri"])
        artist = items[0]['artists'][0]['name'] if items[0].get('artists') else 'Unknown Artist'
        return f"🎵 Now playing album: {items[0]['name']} by {artist}"
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return "❌ Spotify authentication expired. Please visit /login to re-authenticate."
        elif e.http_status == 403:
            return "❌ Spotify Premium required for playback control."
        elif e.http_status == 404:
            return "❌ No active Spotify device found. Please open Spotify on a device first."
        else:
            logger.error(f"Spotify API error: {e}")
            return f"❌ Spotify error: {e}"
    except Exception as e:
        logger.error(f"Error playing album: {e}")
        return f"❌ Error playing album: {e}"

def pause_playback() -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please visit /login to authenticate with Spotify."
    try:
        sp.pause_playback()
        return "⏸️ Playback paused."
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return "❌ Spotify authentication expired. Please visit /login to re-authenticate."
        elif e.http_status == 403:
            return "❌ Spotify Premium required for playback control."
        elif e.http_status == 404:
            return "❌ No active Spotify device found or nothing is playing."
        else:
            logger.error(f"Spotify API error: {e}")
            return f"❌ Spotify error: {e}"
    except Exception as e:
        logger.error(f"Error pausing playback: {e}")
        return f"❌ Error pausing playback: {e}"

def resume_playback() -> str:
    """Resume Spotify playback"""
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please visit /login to authenticate with Spotify."
    try:
        sp.start_playback()
        return "▶️ Playback resumed."
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return "❌ Spotify authentication expired. Please visit /login to re-authenticate."
        elif e.http_status == 403:
            return "❌ Spotify Premium required for playback control."
        elif e.http_status == 404:
            return "❌ No active Spotify device found."
        else:
            logger.error(f"Spotify API error: {e}")
            return f"❌ Spotify error: {e}"
    except Exception as e:
        logger.error(f"Error resuming playback: {e}")
        return f"❌ Error resuming playback: {e}"

def next_track() -> str:
    """Skip to next track"""
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please visit /login to authenticate with Spotify."
    try:
        sp.next_track()
        return "⏭️ Skipped to next track."
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return "❌ Spotify authentication expired. Please visit /login to re-authenticate."
        elif e.http_status == 403:
            return "❌ Spotify Premium required for playback control."
        elif e.http_status == 404:
            return "❌ No active Spotify device found."
        else:
            logger.error(f"Spotify API error: {e}")
            return f"❌ Spotify error: {e}"
    except Exception as e:
        logger.error(f"Error skipping track: {e}")
        return f"❌ Error skipping track: {e}"

def previous_track() -> str:
    """Skip to previous track"""
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please visit /login to authenticate with Spotify."
    try:
        sp.previous_track()
        return "⏮️ Skipped to previous track."
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 401:
            return "❌ Spotify authentication expired. Please visit /login to re-authenticate."
        elif e.http_status == 403:
            return "❌ Spotify Premium required for playback control."
        elif e.http_status == 404:
            return "❌ No active Spotify device found."
        else:
            logger.error(f"Spotify API error: {e}")
            return f"❌ Spotify error: {e}"
    except Exception as e:
        logger.error(f"Error going to previous track: {e}")
        return f"❌ Error going to previous track: {e}"