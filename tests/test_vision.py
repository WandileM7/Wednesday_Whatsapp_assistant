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
