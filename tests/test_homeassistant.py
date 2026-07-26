"""Home Assistant tools: friendly-name resolution, service calls, and the
safety posture (locks readable, never operable; ambiguity never guessed).

Home Assistant is never contacted — httpx is faked and the outgoing service
calls are captured.
"""
import httpx
import pytest

from backend.config import settings
from backend.tools import homeassistant as ha


_STATES = [
    {"entity_id": "light.kitchen", "state": "off",
     "attributes": {"friendly_name": "Kitchen Lights", "brightness": 0}},
    {"entity_id": "light.lounge_lamp", "state": "on",
     "attributes": {"friendly_name": "Lounge Lamp", "brightness": 180}},
    {"entity_id": "light.lounge_strip", "state": "off",
     "attributes": {"friendly_name": "Lounge Strip"}},
    {"entity_id": "climate.hallway", "state": "heat",
     "attributes": {"friendly_name": "Hallway Thermostat", "current_temperature": 19.5}},
    {"entity_id": "scene.movie_night", "state": "scening",
     "attributes": {"friendly_name": "Movie Night"}},
    {"entity_id": "lock.front_door", "state": "locked",
     "attributes": {"friendly_name": "Front Door"}},
    {"entity_id": "sensor.outside_temp", "state": "12.4",
     "attributes": {"friendly_name": "Outside Temperature", "unit_of_measurement": "°C"}},
]


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(settings, "ha_url", "http://ha.test:8123")
    monkeypatch.setattr(settings, "ha_token", "t0ken")


@pytest.fixture
def calls(monkeypatch):
    """Capture POSTed service calls; GET /api/states serves _STATES."""
    posted = []

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **k):
            return httpx.Response(200, json=_STATES,
                                  request=httpx.Request("GET", url))
        async def post(self, url, **k):
            posted.append({"url": url, "json": k.get("json")})
            return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(ha.httpx, "AsyncClient", lambda *a, **k: FakeClient())
    return posted


# ---- configuration ----------------------------------------------------------

async def test_reports_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "ha_url", "")
    out = await ha.home_control("kitchen lights", "on")
    assert "isn't configured" in out


# ---- listing and state ------------------------------------------------------

async def test_lists_controllable_devices(calls):
    rows = await ha.home_list_devices()
    names = [r["name"] for r in rows]
    assert "Kitchen Lights" in names
    # locks and raw sensors aren't controllable, so they're not offered here
    assert "Front Door" not in names
    assert "Outside Temperature" not in names


async def test_list_filters_by_area(calls):
    rows = await ha.home_list_devices(area="lounge")
    assert {r["name"] for r in rows} == {"Lounge Lamp", "Lounge Strip"}


async def test_get_state_includes_useful_attributes(calls):
    out = await ha.home_get_state("hallway thermostat")
    assert out["state"] == "heat" and out["current_temperature"] == 19.5


async def test_lock_is_readable(calls):
    out = await ha.home_get_state("front door")
    assert out == {"name": "Front Door", "state": "locked"}


async def test_sensor_is_readable(calls):
    out = await ha.home_get_state("outside temperature")
    assert out["state"] == "12.4" and out["unit_of_measurement"] == "°C"


# ---- safety: locks are never operable --------------------------------------

async def test_lock_cannot_be_controlled(calls):
    """Voice-unlocking a door is out of scope by design."""
    out = await ha.home_control("front door", "off")
    assert isinstance(out, str) and "Nothing here called" in out
    assert calls == []


# ---- resolution -------------------------------------------------------------

async def test_resolves_by_partial_name(calls):
    out = await ha.home_control("kitchen", "on")
    assert out == "Kitchen Lights on."
    assert calls[0]["url"] == "/api/services/light/turn_on"
    assert calls[0]["json"] == {"entity_id": "light.kitchen"}


async def test_ambiguous_name_asks_rather_than_guessing(calls):
    out = await ha.home_control("lounge", "on")
    assert "Several things match" in out and "Lounge Lamp" in out
    assert calls == []  # nothing was actuated


async def test_exact_name_wins_over_partial(calls):
    # "Lounge Lamp" is exact even though "lounge" matches two things
    out = await ha.home_control("Lounge Lamp", "off")
    assert out == "Lounge Lamp off."
    assert calls[0]["json"] == {"entity_id": "light.lounge_lamp"}


async def test_unknown_device(calls):
    out = await ha.home_control("dungeon", "on")
    assert "Nothing here called" in out
    assert calls == []


# ---- control ----------------------------------------------------------------

async def test_toggle(calls):
    assert await ha.home_control("kitchen", "toggle") == "Kitchen Lights toggled."
    assert calls[0]["url"] == "/api/services/light/toggle"


async def test_bad_action_rejected(calls):
    assert "Action must be" in await ha.home_control("kitchen", "explode")
    assert calls == []


async def test_set_brightness_and_colour(calls):
    out = await ha.home_set_light("kitchen", brightness=40, color="warm white")
    assert calls[0]["url"] == "/api/services/light/turn_on"
    assert calls[0]["json"]["brightness_pct"] == 40
    assert calls[0]["json"]["color_name"] == "warmwhite"
    assert "40%" in out


async def test_zero_brightness_turns_the_light_off(calls):
    out = await ha.home_set_light("kitchen", brightness=0)
    assert calls[0]["url"] == "/api/services/light/turn_off"
    assert out == "Kitchen Lights off."


async def test_set_light_rejects_non_light(calls):
    out = await ha.home_set_light("hallway thermostat", brightness=50)
    assert "Nothing here called" in out


async def test_set_temperature(calls):
    out = await ha.home_set_temperature("hallway", 21)
    assert calls[0]["url"] == "/api/services/climate/set_temperature"
    assert calls[0]["json"]["temperature"] == 21
    assert "21" in out


async def test_insane_temperature_refused(calls):
    assert "sane thermostat range" in await ha.home_set_temperature("hallway", 90)
    assert calls == []


async def test_activate_scene(calls):
    out = await ha.home_activate_scene("movie night")
    assert calls[0]["url"] == "/api/services/scene/turn_on"
    assert out == "Movie Night activated."


# ---- failure ----------------------------------------------------------------

async def test_unreachable_is_graceful(monkeypatch):
    class Dead:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise httpx.ConnectError("no route")
        async def post(self, *a, **k): raise httpx.ConnectError("no route")
    monkeypatch.setattr(ha.httpx, "AsyncClient", lambda *a, **k: Dead())
    assert "Couldn't reach" in await ha.home_control("kitchen", "on")
    assert "Couldn't reach" in await ha.home_list_devices()
    assert "Couldn't reach" in await ha.home_get_state("kitchen")
