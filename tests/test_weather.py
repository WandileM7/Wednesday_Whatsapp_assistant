"""get_weather: geocode a place name, then fetch Open-Meteo's current + daily
forecast, mapping WMO codes to words. No API key, no live network in tests —
httpx is faked. Backs persona.md's marquee "what's the weather?" example, which
previously had no tool behind it."""
import json

import httpx
import pytest

from backend.tools import builtin


def _fake_httpx(monkeypatch, responses):
    """Queue JSON bodies; successive .get() calls return them in order."""
    seq = iter(responses)

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k):
            return httpx.Response(200, json=next(seq),
                                  request=httpx.Request("GET", "https://test"))

    monkeypatch.setattr(builtin.httpx, "AsyncClient", FakeClient)


_GEO = {"results": [{"name": "Cape Town", "country": "South Africa",
                     "latitude": -33.9, "longitude": 18.4}]}
_FORECAST = {
    "current": {"temperature_2m": 23.1, "apparent_temperature": 22.0,
                "relative_humidity_2m": 60, "weather_code": 0,
                "wind_speed_10m": 12.0},
    "daily": {"temperature_2m_max": [24.0, 26.0],
              "temperature_2m_min": [15.0, 16.0],
              "precipitation_probability_max": [10, 40],
              "weather_code": [0, 61]},
}


async def test_returns_current_and_daily_for_a_place(monkeypatch):
    _fake_httpx(monkeypatch, [_GEO, _FORECAST])
    out = await builtin.get_weather("Cape Town")
    assert out["location"] == "Cape Town, South Africa"
    # Temperatures are rendered whole with a unit symbol, never raw decimals —
    # okf/style.md forbids reading "twenty-three point one degrees" aloud.
    assert out["now"]["temp"] == "23°C"
    assert out["now"]["condition"] == "clear sky"
    assert out["forecast"][0] == {"day": "today", "condition": "clear sky",
                                  "high": "24°C", "low": "15°C",
                                  "rain_chance": "10%"}


async def test_imperial_units_switch_the_whole_reply(monkeypatch):
    _fake_httpx(monkeypatch, [_GEO, _FORECAST])
    out = await builtin.get_weather("Cape Town", units="imperial")
    assert out["now"]["temp"].endswith("°F")
    assert out["now"]["wind"].endswith("mph")


async def test_maps_wmo_code_to_words(monkeypatch):
    forecast = {**_FORECAST, "current": {**_FORECAST["current"], "weather_code": 95}}
    _fake_httpx(monkeypatch, [_GEO, forecast])
    out = await builtin.get_weather("Cape Town")
    assert out["now"]["condition"] == "thunderstorm"


async def test_unknown_wmo_code_is_labelled_not_crashing(monkeypatch):
    forecast = {**_FORECAST, "current": {**_FORECAST["current"], "weather_code": 4242}}
    _fake_httpx(monkeypatch, [_GEO, forecast])
    out = await builtin.get_weather("Cape Town")
    assert out["now"]["condition"] == "unknown"


async def test_unknown_place_returns_a_message_not_an_error(monkeypatch):
    _fake_httpx(monkeypatch, [{"results": []}])
    out = await builtin.get_weather("Nowheresville-XYZ")
    assert isinstance(out, str) and "Couldn't find" in out


async def test_falls_back_to_default_location_when_none_given(monkeypatch):
    # "what's the weather?" with no city must resolve to the home location, so
    # the marquee persona example answers without asking where.
    from backend.config import settings
    monkeypatch.setattr(settings, "default_location", "Cape Town")
    geocoded = {}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **k):
            if "geocoding" in url:
                geocoded["name"] = k["params"]["name"]
                return httpx.Response(200, json=_GEO,
                                      request=httpx.Request("GET", url))
            return httpx.Response(200, json=_FORECAST,
                                  request=httpx.Request("GET", url))

    monkeypatch.setattr(builtin.httpx, "AsyncClient", FakeClient)
    out = await builtin.get_weather()
    assert geocoded["name"] == "Cape Town"
    assert out["location"] == "Cape Town, South Africa"


async def test_no_location_and_no_default_asks(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "default_location", "")
    out = await builtin.get_weather()
    assert isinstance(out, str) and "ask the user" in out
