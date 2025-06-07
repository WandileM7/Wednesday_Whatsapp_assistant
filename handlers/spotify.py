import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from main import get_spotify_client

# Initialize with env vars—no interactive prompt
_sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="user-read-playback-state user-modify-playback-state",
    cache_path=None,
    open_browser=False
)


# Manually exchange the saved refresh token for an access token
def play_song(song_name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please GET /login first."
    results = sp.search(q=song_name, type="track", limit=1)
    items = results["tracks"]["items"]
    if not items:
        return f"Couldn't find '{song_name}'."
    uri = items[0]["uri"]
    sp.start_playback(uris=[uri])
    return f"Now playing: {items[0]['name']} by {items[0]['artists'][0]['name']}."

def get_current_song() -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please GET /login first."
    playback = sp.current_playback()
    if not playback or not playback.get("item"):
        return "Nothing is playing right now."
    item = playback["item"]
    return f"Currently: {item['name']} by {item['artists'][0]['name']}."

def play_playlist(name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please GET /login first."
    for pl in sp.current_user_playlists()["items"]:
        if name.lower() in pl["name"].lower():
            sp.start_playback(context_uri=pl["uri"])
            return f"Now playing playlist: {pl['name']}"
    return f"Couldn't find playlist named '{name}'."

def play_album(name: str) -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please GET /login first."
    items = sp.search(q=name, type="album", limit=1)["albums"]["items"]
    if not items:
        return f"Couldn't find album '{name}'."
    sp.start_playback(context_uri=items[0]["uri"])
    return f"Now playing album: {items[0]['name']} by {items[0]['artists'][0]['name']}."

def pause_playback() -> str:
    sp = get_spotify_client()
    if not sp:
        return "❌ Spotify not authenticated. Please GET /login first."
    sp.pause_playback()
    return "Playback paused."