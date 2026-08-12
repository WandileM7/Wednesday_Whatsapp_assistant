"""Vision: the VLM call, the see_image tool, and the WhatsApp photo path."""
import httpx
import pytest

from backend import vision, whatsapp
from backend.config import settings
from backend.tools import builtin

_REQ = httpx.Request("POST", "http://test")


def _ollama_client(text, status=200):
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            return httpx.Response(status, json={"message": {"content": text}}, request=_REQ)
        async def get(self, *a, **k):
            return httpx.Response(200, content=b"\xff\xd8\xff-jpeg-bytes",
                                  headers={"content-type": "image/jpeg"}, request=_REQ)
    return FakeClient


@pytest.fixture(autouse=True)
def _vision_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_vision", True)


async def test_describe_returns_the_models_words(monkeypatch):
    monkeypatch.setattr(vision.httpx, "AsyncClient", _ollama_client("A dog on a beach."))
    assert await vision.describe(b"jpegbytes") == "A dog on a beach."


async def test_describe_is_a_no_op_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_vision", False)
    monkeypatch.setattr(vision.httpx, "AsyncClient", _ollama_client("never called"))
    assert await vision.describe(b"jpegbytes") == ""


async def test_missing_model_degrades_quietly(monkeypatch):
    """A 404 from Ollama means the VLM isn't pulled — say nothing, don't raise."""
    monkeypatch.setattr(vision.httpx, "AsyncClient", _ollama_client("", status=404))
    assert await vision.describe(b"jpegbytes") == ""


async def test_oversized_images_are_refused(monkeypatch):
    monkeypatch.setattr(vision, "_MAX_BYTES", 10)
    monkeypatch.setattr(vision.httpx, "AsyncClient", _ollama_client("never called"))
    assert await vision.describe(b"x" * 11) == ""


async def test_see_image_tool_describes_a_url(monkeypatch):
    monkeypatch.setattr(vision.httpx, "AsyncClient", _ollama_client("A bar chart."))
    assert await builtin.see_image(url="https://x/y.jpg") == "A bar chart."


async def test_see_image_reports_a_fetch_failure(monkeypatch):
    class Broken:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise httpx.ConnectError("no route")
    monkeypatch.setattr(vision.httpx, "AsyncClient", Broken)
    assert "no route" in await builtin.see_image(url="https://x/y.jpg")


# ---- WhatsApp photos --------------------------------------------------------

async def test_whatsapp_image_becomes_described_text(monkeypatch):
    monkeypatch.setattr(whatsapp.httpx, "AsyncClient", _ollama_client("x"))
    async def fake_describe(image, question=""): return "A handwritten shopping list."
    monkeypatch.setattr(vision, "describe", fake_describe)
    text = await whatsapp._describe_image("msg-1", "what does this say?")
    assert "what does this say?" in text
    assert "A handwritten shopping list." in text
    # The description is untrusted content and must be framed as data.
    assert "not instructions" in text


async def test_whatsapp_image_without_vision_still_answers_the_caption(monkeypatch):
    monkeypatch.setattr(whatsapp.httpx, "AsyncClient", _ollama_client("x"))
    async def no_vision(image, question=""): return ""
    monkeypatch.setattr(vision, "describe", no_vision)
    assert await whatsapp._describe_image("msg-1", "is this right?") == "is this right?"


async def test_bare_image_placeholder_is_not_treated_as_a_caption(monkeypatch):
    monkeypatch.setattr(whatsapp.httpx, "AsyncClient", _ollama_client("x"))
    async def no_vision(image, question=""): return ""
    monkeypatch.setattr(vision, "describe", no_vision)
    out = await whatsapp._describe_image("msg-1", "[Image]")
    assert out == "[The user sent an image I couldn't see.]"


# ---- empty-answer fallback --------------------------------------------------
# moondream answers "Describe the square." but returns empty content with
# done_reason=stop for "What colour is the square?" — same image, same model.
# A caption reliably works and usually contains the answer.

def _sequence_client(*replies):
    """Successive POSTs return successive reply strings; records the prompts."""
    prompts = []
    seq = iter(replies)

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            prompts.append(k["json"]["messages"][0]["content"])
            return httpx.Response(200, json={"message": {"content": next(seq)}},
                                  request=_REQ)
    return FakeClient, prompts


async def test_an_empty_answer_falls_back_to_a_description(monkeypatch):
    client, prompts = _sequence_client("", "A red square and a blue circle.")
    monkeypatch.setattr(vision.httpx, "AsyncClient", client)
    out = await vision.describe(b"jpegbytes", "What colour is the square?")
    assert out == "A red square and a blue circle."
    assert prompts == ["What colour is the square?", vision.DEFAULT_PROMPT]


async def test_a_good_answer_does_not_trigger_a_second_call(monkeypatch):
    client, prompts = _sequence_client("Red.", "should not be reached")
    monkeypatch.setattr(vision.httpx, "AsyncClient", client)
    assert await vision.describe(b"jpegbytes", "What colour?") == "Red."
    assert len(prompts) == 1


async def test_an_empty_plain_description_does_not_loop(monkeypatch):
    """No question to fall back from, so exactly one call and an empty result."""
    client, prompts = _sequence_client("", "should not be reached")
    monkeypatch.setattr(vision.httpx, "AsyncClient", client)
    assert await vision.describe(b"jpegbytes") == ""
    assert len(prompts) == 1


# ── Frame buffering and the hosted/local backends ─────────────────────────
# (from the camera-frame side of the module; see backend/vision.py)
import base64, json
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
    # An empty question falls back to DEFAULT_PROMPT — the caption prompt, which
    # asks for text to be transcribed as well. Pinned to the constant rather than
    # its wording so editing the prompt doesn't fail an unrelated transport test.
    assert seen["messages"][0]["content"] == vision.DEFAULT_PROMPT


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
