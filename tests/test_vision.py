"""Vision: frame buffering (RAM-only, expiring) and the VLM call on both
backends. No camera, no model — frames are synthetic and httpx is faked."""
import base64
import json

import httpx
import pytest

from backend import vision
from backend.config import settings
from backend.tools import CURRENT_USER, REGISTRY


_JPEG = base64.b64encode(b"\xff\xd8\xff\xe0 fake jpeg bytes").decode()


@pytest.fixture(autouse=True)
def _clean():
    vision._FRAMES.clear()
    CURRENT_USER.set("v1")
    yield
    vision._FRAMES.clear()
    CURRENT_USER.set("")


# ---- frame buffer -----------------------------------------------------------

def test_stores_and_returns_a_frame():
    assert vision.set_frame("v1", _JPEG) is True
    assert vision.get_frame("v1") == _JPEG


def test_strips_a_data_url_prefix():
    vision.set_frame("v1", f"data:image/jpeg;base64,{_JPEG}")
    assert vision.get_frame("v1") == _JPEG


def test_rejects_garbage_and_empty():
    assert vision.set_frame("v1", "") is False
    assert vision.set_frame("v1", "not base64 !!!") is False
    assert vision.get_frame("v1") is None


def test_rejects_an_oversized_frame():
    assert vision.set_frame("v1", "A" * (vision._MAX_FRAME_BYTES + 4)) is False


def test_newest_frame_replaces_the_old():
    other = base64.b64encode(b"second").decode()
    vision.set_frame("v1", _JPEG); vision.set_frame("v1", other)
    assert vision.get_frame("v1") == other


def test_frames_are_per_user():
    vision.set_frame("v1", _JPEG)
    assert vision.get_frame("v2") is None


def test_stale_frames_expire(monkeypatch):
    vision.set_frame("v1", _JPEG)
    now = vision.time.time() + vision._FRAME_TTL + 1
    monkeypatch.setattr(vision.time, "time", lambda: now)
    assert vision.get_frame("v1") is None


def test_clear_frame():
    vision.set_frame("v1", _JPEG); vision.clear_frame("v1")
    assert vision.get_frame("v1") is None


# ---- describe ---------------------------------------------------------------

@pytest.fixture
def as_hosted(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://fast.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(settings, "llm_model", "vlm-70b")
    monkeypatch.setattr(settings, "vision_model", "")


async def test_hosted_vision_sends_an_image_url(as_hosted):
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [
            {"message": {"content": "A mug of tea."}}]})

    out = await vision.describe(_JPEG, "what is this?",
                                transport=httpx.MockTransport(handler))
    assert out == "A mug of tea."
    parts = seen["messages"][0]["content"]
    assert parts[0]["text"] == "what is this?"
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert seen["model"] == "vlm-70b"


async def test_local_vision_uses_ollama_images_field():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "A cat."}})

    out = await vision.describe(_JPEG, "", transport=httpx.MockTransport(handler))
    assert out == "A cat."
    # Ollama takes images on the message, not as OpenAI content parts
    assert seen["messages"][0]["images"] == [_JPEG]
    assert "Describe what you see" in seen["messages"][0]["content"]


async def test_vision_failure_returns_empty(as_hosted):
    def handler(request):
        return httpx.Response(500, json={})
    out = await vision.describe(_JPEG, "?", transport=httpx.MockTransport(handler))
    assert out == ""


def test_model_defaults(monkeypatch):
    monkeypatch.setattr(settings, "vision_model", "")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", "")
    assert vision.model() == "llava:7b"
    monkeypatch.setattr(settings, "vision_model", "qwen2.5vl:7b")
    assert vision.model() == "qwen2.5vl:7b"


# ---- the look tool ----------------------------------------------------------

async def test_look_without_a_frame():
    out = await REGISTRY["look"]["fn"](question="what is this?")
    assert "camera isn't on" in out


async def test_look_uses_the_stored_frame(monkeypatch):
    vision.set_frame("v1", _JPEG)

    async def fake_describe(image_b64, question, **k):
        assert image_b64 == _JPEG and question == "what am I holding?"
        return "A screwdriver."

    monkeypatch.setattr(vision, "describe", fake_describe)
    assert await REGISTRY["look"]["fn"](question="what am I holding?") == "A screwdriver."


async def test_look_handles_an_unreadable_image(monkeypatch):
    vision.set_frame("v1", _JPEG)
    async def blank(*a, **k): return ""
    monkeypatch.setattr(vision, "describe", blank)
    assert await REGISTRY["look"]["fn"]() == "Couldn't make anything out."


async def test_look_requires_user_context():
    CURRENT_USER.set("")
    assert await REGISTRY["look"]["fn"]() == "No active user context."
