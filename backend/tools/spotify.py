from __future__ import annotations
import httpx
from .. import oauth
from . import register

API = "https://api.spotify.com/v1"
async def _headers(): return {"Authorization": f"Bearer {await oauth.access_token('spotify')}"}

@register("spotify_search","Search Spotify for tracks/albums/artists/playlists.",
    {"type":"object","properties":{"query":{"type":"string"},"kind":{"type":"string","enum":["track","album","artist","playlist"],"default":"track"},"limit":{"type":"integer","default":5}},"required":["query"]})
async def spotify_search(query, kind="track", limit=5):
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c:
        r = await c.get(f"{API}/search", params={"q":query,"type":kind,"limit":limit})
        r.raise_for_status(); items = r.json().get(f"{kind}s",{}).get("items",[])
    return [{"uri":it["uri"],"name":it.get("name"),"artists":", ".join(a["name"] for a in it.get("artists",[]))} for it in items]

@register("spotify_play",
    "Play music on Spotify. For a named song or artist pass query (e.g. "
    "query='Bohemian Rhapsody by Queen') and it is found and played in one step — "
    "do NOT search first. Pass uri only if you already have one. Pass neither to "
    "resume what was paused.",
    {"type":"object","properties":{"query":{"type":"string"},"uri":{"type":"string"}}})
async def spotify_play(query=None, uri=None):
    # `query` exists because the two-hop version did not work: asked to play a
    # named song, a 3B model would skip search→uri→play and simply announce that
    # it had played it, having called nothing. Collapsing the chain into one
    # call removes the step it was skipping.
    picked = None
    if not uri and query:
        results = await spotify_search(query)
        if not results:
            return f"Nothing on Spotify matches {query!r}."
        picked = results[0]
        uri = picked["uri"]
    body = {}
    if uri: body = {"uris":[uri]} if uri.startswith("spotify:track:") else {"context_uri":uri}
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c:
        r = await c.put(f"{API}/me/player/play", json=body or None)
        # 404 here does not reliably mean "no device". Spotify returns it whenever
        # there is no *active playback session* to act on, even while the device
        # list shows an idle phone sitting right there. Naming the device
        # explicitly is what actually starts it.
        if r.status_code == 404:
            devices = (await c.get(f"{API}/me/player/devices")).json().get("devices", [])
            if not devices:
                return ("No Spotify device available. Play something on Spotify for a "
                        "second — a device only becomes controllable once it has.")
            target = next((d for d in devices if d.get("is_active")), devices[0])
            r = await c.put(f"{API}/me/player/play",
                            params={"device_id": target["id"]}, json=body or None)
            if r.status_code == 404:
                return f"Spotify would not start playback on {target.get('name', 'that device')}."
    if r.status_code >= 400:
        return _refusal(r)
    # Name what actually started, so the reply cannot claim a different track.
    return f"Playing {picked['name']} by {picked['artists']}." if picked else "Playing."

@register("spotify_queue",
    "Queue a song to play after the current one. Pass query (e.g. query='Africa by "
    "Toto') — it is found and queued in one step, no search first.",
    {"type":"object","properties":{"query":{"type":"string"},"uri":{"type":"string"}}})
async def spotify_queue(query=None, uri=None):
    picked = None
    if not uri and query:
        found = await spotify_search(query, limit=1)
        if not found: return f"Nothing on Spotify matches {query!r}."
        picked = found[0]; uri = picked["uri"]
    if not uri: return "Which song? Give a query."
    err = await _player("POST", "queue", uri=uri)
    if err: return err
    return f"Queued {picked['name']} by {picked['artists']}." if picked else "Queued."

@register("spotify_now_playing","Get current Spotify track.",{"type":"object","properties":{}})
async def spotify_now_playing():
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.get(f"{API}/me/player/currently-playing")
    if r.status_code == 204: return "Nothing is playing."
    r.raise_for_status(); data = r.json(); item = data.get("item") or {}
    return {"name":item.get("name"),"artists":", ".join(a["name"] for a in item.get("artists",[])),"album":(item.get("album") or {}).get("name"),"is_playing":data.get("is_playing")}

# ── consolidated surfaces ────────────────────────────────────────────────────
# Twelve more capabilities, three more tools. Deliberate: the model already
# reached for spotify_play on only 3 of 14 song requests, and every schema in
# the prompt is another thing for a 3B to sift. Grouping by *what the user
# wants* rather than by endpoint keeps the tool list short and the choice
# obvious — one verb, one argument.

_DEVICE_NEEDED = "No active Spotify device. Play something on Spotify for a second first."


async def _player(method: str, path: str, **params):
    """Call a /me/player endpoint, retrying once against an explicit device.

    Spotify answers 404 whenever there is no active playback *session*, even
    with an idle phone sitting in the device list — naming the device is what
    actually wakes it.
    """
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c:
        r = await c.request(method, f"{API}/me/player/{path}", params=params or None)
        if r.status_code == 404:
            devices = (await c.get(f"{API}/me/player/devices")).json().get("devices", [])
            if not devices:
                return _DEVICE_NEEDED
            target = next((d for d in devices if d.get("is_active")), devices[0])
            r = await c.request(method, f"{API}/me/player/{path}",
                                params={**(params or {}), "device_id": target["id"]})
        if r.status_code >= 400:
            return _refusal(r)
    return None      # success


def _refusal(r) -> str:
    """Spotify's 403s are not interchangeable, and guessing sends the user after
    the wrong fix. "Cannot control device volume" on a Premium account is a
    *device* limitation — a phone reports supports_volume: false — and telling
    someone to buy Premium they already have wastes their afternoon.
    """
    try:
        err = (r.json() or {}).get("error") or {}
    except Exception:
        err = {}
    reason, message = err.get("reason", ""), err.get("message", "")
    if reason == "PREMIUM_REQUIRED":
        return "That needs Spotify Premium — the free tier can't be controlled remotely."
    if reason.startswith("VOLUME_CONTROL"):
        return ("That device won't take a volume command from Spotify — phones usually "
                "refuse. Use the phone's own volume, or move playback to a desktop first.")
    if reason == "NO_ACTIVE_DEVICE":
        return _DEVICE_NEEDED
    if reason == "UNKNOWN" and message:
        return f"Spotify refused: {message}"
    return f"Spotify returned {r.status_code}" + (f" — {message}" if message else ".")


@register("spotify_control",
    "Control playback: pause, resume, next, previous, shuffle, repeat, volume, seek, "
    "or move playback to another device. `value` is the volume percent (0-100), the "
    "seek position in seconds, on/off for shuffle, off/track/all for repeat, or a "
    "device name for transfer. To play a specific song use spotify_play instead.",
    {"type":"object","properties":{
        "action":{"type":"string","enum":["pause","resume","next","previous","shuffle",
                                          "repeat","volume","seek","transfer"]},
        "value":{"type":"string"}},
     "required":["action"]})
async def spotify_control(action: str, value: str = ""):
    action, value = action.strip().lower(), (value or "").strip()

    if action == "pause":    return await _player("PUT", "pause") or "Paused."
    if action == "resume":   return await _player("PUT", "play") or "Playing."
    if action == "next":     return await _player("POST", "next") or "Skipped."
    if action == "previous": return await _player("POST", "previous") or "Back a track."

    if action == "shuffle":
        on = value.lower() not in ("off", "false", "no", "0")
        return await _player("PUT", "shuffle", state=str(on).lower()) or \
            f"Shuffle {'on' if on else 'off'}."

    if action == "repeat":
        state = {"off": "off", "track": "track", "one": "track",
                 "all": "context", "on": "context"}.get(value.lower(), "context")
        return await _player("PUT", "repeat", state=state) or f"Repeat {state}."

    if action == "volume":
        try: pct = max(0, min(100, int(float(value))))
        except ValueError: return f"Volume needs a number 0-100, got {value!r}."
        return await _player("PUT", "volume", volume_percent=pct) or f"Volume {pct}%."

    if action == "seek":
        try: ms = int(float(value) * 1000)
        except ValueError: return f"Seek needs seconds, got {value!r}."
        return await _player("PUT", "seek", position_ms=ms) or f"Jumped to {value}s."

    if action == "transfer":
        async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c:
            devices = (await c.get(f"{API}/me/player/devices")).json().get("devices", [])
            if not devices: return _DEVICE_NEEDED
            match = next((d for d in devices if value.lower() in d.get("name", "").lower()),
                         None) if value else devices[0]
            if not match:
                names = ", ".join(d.get("name", "?") for d in devices)
                return f"No device called {value!r}. Available: {names}."
            r = await c.put(f"{API}/me/player",
                            json={"device_ids": [match["id"]], "play": True})
            if r.status_code >= 400: return f"Spotify returned {r.status_code}."
            return f"Moved playback to {match.get('name')}."

    return f"Unknown action {action!r}."


_LIBRARY = {
    "top_tracks":  ("/me/top/tracks", "items"),
    "top_artists": ("/me/top/artists", "items"),
    "recent":      ("/me/player/recently-played", "items"),
    "saved":       ("/me/tracks", "items"),
    "playlists":   ("/me/playlists", "items"),
    "following":   ("/me/following", "artists"),
    "devices":     ("/me/player/devices", "devices"),
}


@register("spotify_library",
    "Read the user's own Spotify: top_tracks or top_artists (their most played), "
    "recent (recently played), saved (liked songs), playlists, or following. "
    "`period` applies to top_* only: short (4 weeks), medium (6 months), long (years).",
    {"type":"object","properties":{
        "kind":{"type":"string","enum":list(_LIBRARY)},
        "period":{"type":"string","enum":["short","medium","long"],"default":"medium"},
        "limit":{"type":"integer","default":10}},
     "required":["kind"]})
async def spotify_library(kind: str, period: str = "medium", limit: int = 10):
    path, key = _LIBRARY.get(kind, (None, None))
    if not path: return f"Unknown kind {kind!r}. Try: {', '.join(_LIBRARY)}."
    params = {"limit": max(1, min(50, int(limit)))}
    if kind.startswith("top_"):
        params["time_range"] = {"short": "short_term", "medium": "medium_term",
                                "long": "long_term"}.get(period, "medium_term")
    if kind == "following":
        params["type"] = "artist"

    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c:
        r = await c.get(f"{API}{path}", params=params)
    if r.status_code >= 400: return f"Spotify returned {r.status_code}."
    payload = r.json()
    items = (payload.get(key) or {}).get("items") if kind == "following" else payload.get(key, [])
    return [_describe(it) for it in (items or [])] or f"Nothing under {kind}."


def _describe(item: dict) -> str:
    """One readable line per item, whatever shape the endpoint returned."""
    track = item.get("track") or item                      # recently-played / saved wrap it
    if track.get("type") == "artist" or "genres" in track:
        return track.get("name", "?")
    if track.get("type") == "playlist" or "tracks" in track and "album" not in track:
        n = (track.get("tracks") or {}).get("total")
        return f"{track.get('name', '?')}" + (f" ({n} tracks)" if n is not None else "")
    artists = ", ".join(a["name"] for a in track.get("artists", []))
    return f"{track.get('name', '?')}" + (f" — {artists}" if artists else "")


@register("spotify_playlist",
    "Create a playlist, or add a song to one. action=create needs name; action=add "
    "needs name (the playlist) and query (the song to find and add).",
    {"type":"object","properties":{
        "action":{"type":"string","enum":["create","add"]},
        "name":{"type":"string"},
        "query":{"type":"string"},
        "description":{"type":"string"}},
     "required":["action","name"]})
async def spotify_playlist(action: str, name: str, query: str = "", description: str = ""):
    async with httpx.AsyncClient(timeout=25, headers=await _headers()) as c:
        if action == "create":
            me = (await c.get(f"{API}/me")).json()
            r = await c.post(f"{API}/users/{me['id']}/playlists",
                             json={"name": name, "description": description, "public": False})
            if r.status_code >= 400: return f"Spotify returned {r.status_code}."
            return f"Created the playlist {name!r}."

        if action == "add":
            if not query: return "Which song? Give a query."
            found = await spotify_search(query, limit=1)
            if not found: return f"Nothing on Spotify matches {query!r}."
            track = found[0]
            lists = (await c.get(f"{API}/me/playlists", params={"limit": 50})).json().get("items", [])
            match = next((p for p in lists if name.lower() in (p.get("name") or "").lower()), None)
            if not match:
                names = ", ".join(p.get("name", "?") for p in lists[:8])
                return f"No playlist called {name!r}. Yours: {names}."
            r = await c.post(f"{API}/playlists/{match['id']}/tracks",
                             json={"uris": [track["uri"]]})
            if r.status_code >= 400: return f"Spotify returned {r.status_code}."
            return f"Added {track['name']} by {track['artists']} to {match['name']}."

    return f"Unknown action {action!r}."
