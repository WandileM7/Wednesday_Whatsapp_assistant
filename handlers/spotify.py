import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from handlers.spotify_client import get_spotify_client


def play_song(song_name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please set SPOTIFY_REFRESH_TOKEN."
    try:
        results = sp.search(q=song_name, type="track", limit=1)
        items = results["tracks"]["items"]
        if not items:
            return f"Couldn't find '{song_name}'."
        uri = items[0]["uri"]
        sp.start_playback(uris=[uri])
        return f"Now playing: {items[0]['name']} by {items[0]['artists'][0]['name']}."
    except Exception as e:
        return f"Error playing song: {e}"

def get_current_song() -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please set SPOTIFY_REFRESH_TOKEN."
    try:
        playback = sp.current_playback()
        if not playback or not playback.get("item"):
            return "Nothing is playing right now."
        item = playback["item"]
        return f"Currently: {item['name']} by {item['artists'][0]['name']}."
    except Exception as e:
        return f"Error getting current song: {e}"

def play_playlist(name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please set SPOTIFY_REFRESH_TOKEN."
    try:
        for pl in sp.current_user_playlists()["items"]:
            if name.lower() in pl["name"].lower():
                sp.start_playback(context_uri=pl["uri"])
                return f"Now playing playlist: {pl['name']}"
        return f"Couldn't find playlist named '{name}'."
    except Exception as e:
        return f"Error playing playlist: {e}"

def play_album(name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please set SPOTIFY_REFRESH_TOKEN."
    try:
        items = sp.search(q=name, type="album", limit=1)["albums"]["items"]
        if not items:
            return f"Couldn't find album '{name}'."
        sp.start_playback(context_uri=items[0]["uri"])
        return f"Now playing album: {items[0]['name']} by {items[0]['artists'][0]['name']}."
    except Exception as e:
        return f"Error playing album: {e}"

def pause_playback() -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please set SPOTIFY_REFRESH_TOKEN."
    try:
        sp.pause_playback()
        return "Playback paused."
    except Exception as e:
        return f"Error pausing playback: {e}"