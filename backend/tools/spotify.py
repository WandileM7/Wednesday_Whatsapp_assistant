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

@register("spotify_play","Start/resume Spotify playback. Pass URI to play specific item.",
    {"type":"object","properties":{"uri":{"type":"string"}}})
async def spotify_play(uri=None):
    body = {}
    if uri: body = {"uris":[uri]} if uri.startswith("spotify:track:") else {"context_uri":uri}
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c:
        r = await c.put(f"{API}/me/player/play", json=body or None)
    if r.status_code == 404: return "No active Spotify device. Open Spotify on a device first."
    r.raise_for_status(); return "Playing."

@register("spotify_pause","Pause Spotify.",{"type":"object","properties":{}})
async def spotify_pause():
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.put(f"{API}/me/player/pause")
    r.raise_for_status(); return "Paused."

@register("spotify_next","Skip to next track.",{"type":"object","properties":{}})
async def spotify_next():
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.post(f"{API}/me/player/next")
    r.raise_for_status(); return "Skipped."

@register("spotify_queue","Queue a track on Spotify.",
    {"type":"object","properties":{"uri":{"type":"string"}},"required":["uri"]})
async def spotify_queue(uri):
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.post(f"{API}/me/player/queue", params={"uri":uri})
    r.raise_for_status(); return "Queued."

@register("spotify_now_playing","Get current Spotify track.",{"type":"object","properties":{}})
async def spotify_now_playing():
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.get(f"{API}/me/player/currently-playing")
    if r.status_code == 204: return "Nothing is playing."
    r.raise_for_status(); data = r.json(); item = data.get("item") or {}
    return {"name":item.get("name"),"artists":", ".join(a["name"] for a in item.get("artists",[])),"album":(item.get("album") or {}).get("name"),"is_playing":data.get("is_playing")}