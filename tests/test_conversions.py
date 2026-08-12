"""Unit / temperature / currency conversion and world time.

Units and time are pure stdlib, so they're checked against known values.
Currency is the only networked one and is faked.
"""
import httpx
import pytest

from backend.tools import builtin


# ---- units ------------------------------------------------------------------

async def test_length_conversion():
    out = await builtin.convert_units(26.0, "miles", "km")
    assert out["value"] == pytest.approx(41.8432, abs=1e-3)


async def test_mass_conversion():
    out = await builtin.convert_units(180, "lb", "kg")
    assert out["value"] == pytest.approx(81.6466, abs=1e-3)


async def test_round_trip_is_stable():
    there = await builtin.convert_units(5, "km", "miles")
    back = await builtin.convert_units(there["value"], "miles", "km")
    assert back["value"] == pytest.approx(5, abs=1e-3)


async def test_unit_aliases_and_case():
    a = await builtin.convert_units(1, "Metre", "CM")
    assert a["value"] == pytest.approx(100)


async def test_unknown_unit_is_reported():
    assert "Unknown unit" in await builtin.convert_units(1, "smoot", "m")


async def test_cross_dimension_is_refused():
    out = await builtin.convert_units(1, "kg", "m")
    assert "Can't convert mass to length" in out


# ---- temperature ------------------------------------------------------------

async def test_fahrenheit_to_celsius():
    out = await builtin.convert_units(72, "f", "c")
    assert out["value"] == pytest.approx(22.2222, abs=1e-3)


async def test_celsius_to_kelvin():
    out = await builtin.convert_units(0, "c", "kelvin")
    assert out["value"] == pytest.approx(273.15)


async def test_temperature_mixed_with_normal_unit_refused():
    out = await builtin.convert_units(20, "c", "km")
    assert "one is a temperature" in out


# ---- world time -------------------------------------------------------------

async def test_world_time_by_iana_zone():
    out = await builtin.world_time("Europe/Lisbon")
    assert out["place"] == "Europe/Lisbon"
    assert len(out["time"]) == 5 and ":" in out["time"]


async def test_world_time_by_city_name():
    out = await builtin.world_time("Tokyo")
    assert out["place"].endswith("Tokyo")


async def test_world_time_handles_two_word_city():
    out = await builtin.world_time("New York")
    assert out["place"].endswith("New York")


async def test_world_time_unknown_place():
    out = await builtin.world_time("Atlantis")
    assert isinstance(out, str) and "Don't know a timezone" in out


# ---- currency ---------------------------------------------------------------

def _fake_currency(monkeypatch, payload=None, boom=False):
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **k):
            if boom: raise httpx.ConnectError("offline")
            return httpx.Response(200, json=payload,
                                  request=httpx.Request("GET", url))
    monkeypatch.setattr(builtin.httpx, "AsyncClient", FakeClient)


async def test_currency_conversion(monkeypatch):
    _fake_currency(monkeypatch, {"date": "2026-07-26", "rates": {"ZAR": 1850.5}})
    out = await builtin.convert_currency(100, "usd", "zar")
    assert out["amount"] == 1850.5 and out["currency"] == "ZAR"
    assert out["from"] == "100 USD"


async def test_same_currency_short_circuits(monkeypatch):
    _fake_currency(monkeypatch, boom=True)  # must not be called at all
    out = await builtin.convert_currency(50, "ZAR", "zar")
    assert out == {"amount": 50, "currency": "ZAR", "rate": 1.0}


async def test_currency_service_down_is_graceful(monkeypatch):
    _fake_currency(monkeypatch, boom=True)
    out = await builtin.convert_currency(100, "USD", "ZAR")
    assert isinstance(out, str) and "Couldn't reach" in out


async def test_unknown_currency_code(monkeypatch):
    _fake_currency(monkeypatch, {"date": "2026-07-26", "rates": {}})
    out = await builtin.convert_currency(100, "USD", "XYZ")
    assert "No rate for USD->XYZ" in out
