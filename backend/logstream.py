"""In-process pub/sub for backend log records, so a browser HUD can tail the
live backend logs over SSE.

A :class:`logging.Handler` is attached to the root logger; every record it sees
is normalised to a small JSON-friendly dict, appended to a bounded ring buffer
(for replay on connect), and fanned out to any subscribed asyncio queues. This
keeps the transport decoupled from the logging call sites — anything that goes
through ``logging`` anywhere in the backend flows through to the UI for free.
"""
from __future__ import annotations
import asyncio, logging, time
from collections import deque
from typing import Any, Deque

# Ring buffer of the most recent records so a freshly-opened tab has context
# instead of an empty screen until the next log line happens.
_BUFFER: Deque[dict[str, Any]] = deque(maxlen=400)
_subscribers: set[asyncio.Queue] = set()
_loop: asyncio.AbstractEventLoop | None = None
_seq = 0

# Noisy per-line access/health logs that would drown the signal in the HUD.
_MUTE = ("GET /logs/stream", "GET /telemetry", "GET /health", "GET /doctor")


def _publish(record: dict[str, Any]) -> None:
    _BUFFER.append(record)
    for q in list(_subscribers):
        try:
            q.put_nowait(record)
        except asyncio.QueueFull:
            pass


class _BroadcastHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        global _seq
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        if any(m in msg for m in _MUTE):
            return
        _seq += 1
        entry = {
            "seq": _seq,
            "ts": record.created,
            "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": msg,
        }
        if record.exc_info:
            entry["msg"] += "\n" + self.format(record).split("\n", 1)[-1]
        # The handler runs on whatever thread logged; hop back onto the API loop
        # so we only ever touch the subscriber queues from one thread.
        if _loop and _loop.is_running():
            _loop.call_soon_threadsafe(_publish, entry)
        else:
            _publish(entry)


def install() -> None:
    """Attach the broadcast handler to the root logger (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h, _BroadcastHandler) for h in root.handlers):
        return
    handler = _BroadcastHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def recent(limit: int = 200) -> list[dict[str, Any]]:
    return list(_BUFFER)[-limit:]


def event(msg: str, level: str = "INFO", logger: str = "wednesday.flow") -> None:
    """Emit a structured flow event straight into the stream (also logs it)."""
    logging.getLogger(logger).log(getattr(logging, level, logging.INFO), msg)
