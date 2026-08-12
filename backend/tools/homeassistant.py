"""Home Assistant control — lights, climate, media, scenes, sensors.

Off unless HA_URL and HA_TOKEN are set, in which case the tools register but
report a clear "not configured" instead of failing obscurely.

Entities are addressed by friendly name rather than entity_id: the model should
say "kitchen lights", not "light.kitchen_ceiling_downlights_2". `_resolve` maps
a spoken name onto an entity by exact match, then unique substring — and
deliberately refuses to guess between several matches, because turning off the
wrong room is a bad way to learn the difference.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from . import register

log = logging.getLogger(__name__)

# Domains we can actuate. Deliberately excludes `lock`: these actions are not
# approval-gated (asking permission for a light switch would destroy the point
# of an ambient assistant), and everything here is cheap and reversible — a
# wrongly-toggled lamp costs nothing. Unlocking a door on a voice command is a
# different class of risk entirely, so locks stay readable but never operable.
_CONTROLLABLE = ("light", "switch", "fan", "climate", "media_player", "cover",
                 "scene", "script", "input_boolean")
# Additionally readable — knowing the door is locked is useful and harmless.
_READABLE = _CONTROLLABLE + ("lock", "sensor", "binary_sensor", "person",
                             "device_tracker")


def configured() -> bool:
    return bool(settings.ha_url and settings.ha_token)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.ha_url.rstrip("/"),
        timeout=15,
        headers={"Authorization": f"Bearer {settings.ha_token}",
                 "Content-Type": "application/json"})


async def _states() -> list[dict]:
    async with _client() as c:
        r = await c.get("/api/states")
        r.raise_for_status()
        return r.json()


def _name(entity: dict) -> str:
    return (entity.get("attributes", {}).get("friendly_name")
            or entity.get("entity_id", "")).strip()


async def _resolve(name: str, domains: tuple[str, ...] = _CONTROLLABLE):
    """Find one entity by friendly name. Returns the entity dict, or a string
    explaining why it couldn't (unknown / ambiguous) — never a wrong guess."""
    needle = name.strip().lower()
    if not needle:
        return "Which one?"
    candidates = [e for e in await _states()
                  if e.get("entity_id", "").split(".")[0] in domains]
    exact = [e for e in candidates
             if _name(e).lower() == needle or e["entity_id"].lower() == needle]
    if len(exact) == 1:
        return exact[0]
    partial = [e for e in candidates if needle in _name(e).lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        return f"Nothing here called {name.strip()!r}."
    names = ", ".join(sorted(_name(e) for e in partial)[:6])
    return f"Several things match {name.strip()!r}: {names}. Which one?"


async def _call_service(domain: str, service: str, data: dict) -> None:
    async with _client() as c:
        r = await c.post(f"/api/services/{domain}/{service}", json=data)
        r.raise_for_status()


def _guard():
    return None if configured() else \
        "Home Assistant isn't configured — set HA_URL and HA_TOKEN."


@register("home_list_devices",
    "List controllable smart-home devices and their current state. Use to find "
    "the right name before controlling something.",
    {"type":"object","properties":{"area":{"type":"string","description":"Optional filter, matched against the device name"}}})
async def home_list_devices(area: str = ""):
    if msg := _guard(): return msg
    try:
        entities = await _states()
    except Exception as exc:
        log.warning("HA unreachable: %s", exc)
        return "Couldn't reach Home Assistant."
    rows = [{"name": _name(e), "state": e.get("state"),
             "kind": e["entity_id"].split(".")[0]}
            for e in entities
            if e.get("entity_id", "").split(".")[0] in _CONTROLLABLE and _name(e)]
    if area.strip():
        needle = area.strip().lower()
        rows = [r for r in rows if needle in r["name"].lower()]
    return sorted(rows, key=lambda r: r["name"]) or "No matching devices."


@register("home_get_state",
    "Current state of one smart-home device or sensor, by name (e.g. 'kitchen "
    "lights', 'front door', 'living room temperature').",
    {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]})
async def home_get_state(name: str):
    if msg := _guard(): return msg
    try:
        found = await _resolve(name, _READABLE)
    except Exception as exc:
        log.warning("HA unreachable: %s", exc)
        return "Couldn't reach Home Assistant."
    if isinstance(found, str): return found
    attrs = found.get("attributes", {})
    out = {"name": _name(found), "state": found.get("state")}
    for key in ("brightness", "current_temperature", "temperature",
                "media_title", "volume_level", "unit_of_measurement"):
        if key in attrs:
            out[key] = attrs[key]
    return out


@register("home_control",
    "Turn a smart-home device on or off, or toggle it, by name (lights, "
    "switches, fans, media players, blinds). Just do it — don't ask permission.",
    {"type":"object","properties":{"name":{"type":"string"},
     "action":{"type":"string","enum":["on","off","toggle"]}},"required":["name","action"]})
async def home_control(name: str, action: str):
    if msg := _guard(): return msg
    act = action.strip().lower()
    if act not in ("on", "off", "toggle"):
        return "Action must be on, off or toggle."
    try:
        found = await _resolve(name)
        if isinstance(found, str): return found
        domain = found["entity_id"].split(".")[0]
        service = {"on": "turn_on", "off": "turn_off", "toggle": "toggle"}[act]
        await _call_service(domain, service, {"entity_id": found["entity_id"]})
    except Exception as exc:
        log.warning("HA control failed: %s", exc)
        return "Couldn't reach Home Assistant."
    return f"{_name(found)} {'toggled' if act == 'toggle' else act}."


@register("home_set_light",
    "Set a light's brightness (0-100) and/or colour by name.",
    {"type":"object","properties":{"name":{"type":"string"},
     "brightness":{"type":"integer","minimum":0,"maximum":100},
     "color":{"type":"string","description":"A colour name such as 'warm white' or 'red'"}},
     "required":["name"]})
async def home_set_light(name: str, brightness: int | None = None, color: str = ""):
    if msg := _guard(): return msg
    try:
        found = await _resolve(name, ("light",))
        if isinstance(found, str): return found
        data: dict = {"entity_id": found["entity_id"]}
        if brightness is not None:
            if not 0 <= brightness <= 100:
                return "Brightness is a percentage, 0 to 100."
            if brightness == 0:
                await _call_service("light", "turn_off", data)
                return f"{_name(found)} off."
            data["brightness_pct"] = brightness
        if color.strip():
            data["color_name"] = color.strip().lower().replace(" ", "")
        await _call_service("light", "turn_on", data)
    except Exception as exc:
        log.warning("HA light failed: %s", exc)
        return "Couldn't reach Home Assistant."
    bits = [f"{brightness}%"] if brightness is not None else []
    if color.strip(): bits.append(color.strip())
    return f"{_name(found)} set" + (f" to {', '.join(bits)}." if bits else ".")


@register("home_set_temperature",
    "Set a thermostat's target temperature (°C) by name.",
    {"type":"object","properties":{"name":{"type":"string"},"celsius":{"type":"number"}},
     "required":["name","celsius"]})
async def home_set_temperature(name: str, celsius: float):
    if msg := _guard(): return msg
    if not 5 <= celsius <= 35:
        return "That's outside any sane thermostat range (5-35°C)."
    try:
        found = await _resolve(name, ("climate",))
        if isinstance(found, str): return found
        await _call_service("climate", "set_temperature",
                            {"entity_id": found["entity_id"], "temperature": celsius})
    except Exception as exc:
        log.warning("HA climate failed: %s", exc)
        return "Couldn't reach Home Assistant."
    return f"{_name(found)} set to {celsius}°C."


@register("home_activate_scene",
    "Activate a Home Assistant scene or script by name (e.g. 'movie night').",
    {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]})
async def home_activate_scene(name: str):
    if msg := _guard(): return msg
    try:
        found = await _resolve(name, ("scene", "script"))
        if isinstance(found, str): return found
        domain = found["entity_id"].split(".")[0]
        await _call_service(domain, "turn_on", {"entity_id": found["entity_id"]})
    except Exception as exc:
        log.warning("HA scene failed: %s", exc)
        return "Couldn't reach Home Assistant."
    return f"{_name(found)} activated."
