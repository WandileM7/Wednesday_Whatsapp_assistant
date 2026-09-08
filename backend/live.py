"""Registry of connected WebSocket clients per user, so proactive messages
(reminders, heartbeat pings) can reach an open browser tab."""
from __future__ import annotations
import logging
from fastapi import WebSocket

log = logging.getLogger(__name__)
_clients: dict[str, set[WebSocket]] = {}


def register(user: str, ws: WebSocket) -> None:
    _clients.setdefault(user, set()).add(ws)


def unregister(user: str, ws: WebSocket) -> None:
    _clients.get(user, set()).discard(ws)


async def push(user: str, text: str) -> bool:
    """Send a notice to every open tab for this user. True if anyone got it."""
    delivered = False
    for ws in list(_clients.get(user, ())):
        try:
            await ws.send_json({"type": "notice", "text": text})
            delivered = True
        except Exception:
            log.debug("dropping dead ws for %s", user)
            unregister(user, ws)
    return delivered
