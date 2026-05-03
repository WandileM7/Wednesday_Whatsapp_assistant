from __future__ import annotations
import base64, datetime as _dt, logging
import httpx
from . import db
from .config import settings

log = logging.getLogger(__name__)
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTHZ_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_AUTHZ_URL = "https://accounts.spotify.com/authorize"

def _redirect(service): return f"{settings.public_url.rstrip('/')}/auth/{service}/callback"

def google_authz_url():
    from urllib.parse import urlencode
    return GOOGLE_AUTHZ_URL + "?" + urlencode({"client_id": settings.google_client_id,
        "redirect_uri": _redirect("google"), "response_type": "code",
        "scope": settings.google_scopes, "access_type": "offline", "prompt": "consent"})

def spotify_authz_url():
    from urllib.parse import urlencode
    return SPOTIFY_AUTHZ_URL + "?" + urlencode({"client_id": settings.spotify_client_id,
        "redirect_uri": _redirect("spotify"), "response_type": "code", "scope": settings.spotify_scopes})

async def exchange_google_code(code):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(GOOGLE_TOKEN_URL, data={"code": code, "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret, "redirect_uri": _redirect("google"),
            "grant_type": "authorization_code"})
        r.raise_for_status(); data = r.json()
    expires = _dt.datetime.utcnow() + _dt.timedelta(seconds=data.get("expires_in", 3600))
    await db.save_token("google", data["access_token"], data.get("refresh_token"), expires, data.get("scope"))

async def exchange_spotify_code(code):
    auth = base64.b64encode(f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(SPOTIFY_TOKEN_URL, headers={"Authorization": f"Basic {auth}"},
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": _redirect("spotify")})
        r.raise_for_status(); data = r.json()
    expires = _dt.datetime.utcnow() + _dt.timedelta(seconds=data.get("expires_in", 3600))
    await db.save_token("spotify", data["access_token"], data.get("refresh_token"), expires, data.get("scope"))

async def access_token(service: str) -> str:
    token = await db.get_token(service)
    if token is None:
        raise RuntimeError(f"{service} not connected. Visit /auth/{service}")
    expired = token.expires_at and token.expires_at <= _dt.datetime.utcnow() + _dt.timedelta(seconds=30)
    if not expired: return token.access_token
    if not token.refresh_token:
        raise RuntimeError(f"{service} token expired, no refresh_token. Re-link.")
    if service == "google":
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(GOOGLE_TOKEN_URL, data={"refresh_token": token.refresh_token,
                "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token"})
            r.raise_for_status(); data = r.json()
    else:
        auth = base64.b64encode(f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(SPOTIFY_TOKEN_URL, headers={"Authorization": f"Basic {auth}"},
                data={"grant_type": "refresh_token", "refresh_token": token.refresh_token})
            r.raise_for_status(); data = r.json()
    new_expires = _dt.datetime.utcnow() + _dt.timedelta(seconds=data.get("expires_in", 3600))
    await db.save_token(service, data["access_token"],
        data.get("refresh_token") or token.refresh_token, new_expires, data.get("scope") or token.scope)
    return data["access_token"]