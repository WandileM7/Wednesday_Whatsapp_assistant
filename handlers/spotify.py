import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Spotify OAuth2 setup (using refresh token from ENV)
_sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="user-read-playback-state,user-modify-playback-state",
    cache_path=None  # we’ll handle refresh manually
)



# Immediately refresh the access token using your saved refresh token
initial_token_info = {
    "refresh_token": os.getenv("SPOTIFY_REFRESH_TOKEN"),
    "scope": "user-read-playback-state,user-modify-playback-state"
}
token_info = _sp_oauth.refresh_access_token(initial_token_info["refresh_token"])

# Assign the returned token_info so Spotipy can manage expiration/refresh
_sp_oauth.cache_handler.save_token_info(token_info)
_sp = spotipy.Spotify(auth_manager=_sp_oauth)


def play_song(song_name: str) -> str:
    results = _sp.search(q=song_name, type="track", limit=1)
    items = results.get("tracks", {}).get("items", [])
    if not items:
        return f"Couldn't find '{song_name}' on Spotify."

    track = items[0]
    uri = track["uri"]
    current = _sp.current_playback()
    if current and current.get("is_playing") and current.get("item", {}).get("uri") == uri:
        return f"{track['name']} by {track['artists'][0]['name']} is already playing."

    _sp.start_playback(uris=[uri])
    return f"Now playing: {track['name']} by {track['artists'][0]['name']}."


def get_current_song() -> str:
    playback = _sp.current_playback()
    if not playback or not playback.get("item"):
        return "Nothing is playing right now."
    item = playback["item"]
    return f"Currently: {item['name']} by {item['artists'][0]['name']}."


def play_playlist(name: str) -> str:
    playlists = _sp.current_user_playlists()["items"]
    for playlist in playlists:
        if name.lower() in playlist["name"].lower():
            _sp.start_playback(context_uri=playlist["uri"])
            return f"Now playing playlist: {playlist['name']}"
    return f"Couldn't find playlist named '{name}'."


def play_album(name: str) -> str:
    results = _sp.search(q=name, type="album", limit=1)
    items = results.get("albums", {}).get("items", [])
    if not items:
        return f"Couldn't find album '{name}'."
    _sp.start_playback(context_uri=items[0]["uri"])
    return f"Now playing album: {items[0]['name']} by {items[0]['artists'][0]['name']}."


def pause_playback() -> str:
    _sp.pause_playback()
    return "Playback paused."


# Spotify OAuth2 setup (non-interactive)
