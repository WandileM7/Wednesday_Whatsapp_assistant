"""Markdown flattening for phone surfaces.

Both qwen2.5:3b and llama3.1:8b failed the same eval case — asked for three
dinner ideas over iMessage they answered with `**bold**` and `* bullets`,
despite a system note forbidding both. The instruction loses to the format
prior, so the transform is deterministic instead.
"""
import pytest

from backend.plaintext import flatten


@pytest.mark.parametrize("raw, expected", [
    ("**Baked Salmon** with lemon", "Baked Salmon with lemon"),
    ("Try the *salmon*.", "Try the salmon."),
    ("This is _emphasised_ properly.", "This is emphasised properly."),
    ("***very bold***", "very bold"),
    ("## Dinner", "Dinner"),
    ("> quoted line", "quoted line"),
    ("Use `ollama pull` first.", "Use ollama pull first."),
])
def test_strips_inline_markdown(raw, expected):
    assert flatten(raw) == expected


def test_bullets_become_readable_not_deleted():
    """Structure is kept — the goal is text that reads right in a bubble, not
    text with the shape stripped out."""
    assert flatten("* Salmon\n- Chicken\n+ Beef") == "• Salmon\n• Chicken\n• Beef"


def test_numbered_lists_survive():
    assert flatten("1. **Salmon**\n2. **Chicken**") == "1. Salmon\n2. Chicken"


def test_links_keep_their_target():
    """Speech drops URLs because they are unreadable aloud; a bubble keeps them
    because they are tappable."""
    assert flatten("See [the docs](https://example.com/g).") == \
        "See the docs (https://example.com/g)."


def test_a_link_whose_label_is_the_url_is_not_doubled():
    assert flatten("[https://example.com](https://example.com)") == "https://example.com"


@pytest.mark.parametrize("raw", [
    "snake_case_name and file_name_here stay intact",
    "Path: /home/wandile/my_project/main_file.py",
    "Read https://example.com — no markdown here.",
    "Nothing special here at all.",
    "",
])
def test_leaves_ordinary_text_alone(raw):
    """Underscore emphasis needs word boundaries. Mangling an identifier or a
    filename would be worse than the asterisks ever were."""
    assert flatten(raw) == raw


def test_code_fences_keep_their_contents():
    assert flatten("Run this:\n```bash\nollama pull llama3.1:8b\n```") == \
        "Run this:\nollama pull llama3.1:8b"


# --- wiring ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_reply_flattens_only_on_phone_surfaces(monkeypatch):
    """The transform is surface-conditional: a bubble renders asterisks
    literally, the web console renders markdown properly and should keep it."""
    from backend import agent

    async def fake_stream(channel, user_text, surface=None):
        yield {"type": "delta", "text": "Ideas:\n\n* **Salmon**\n* Chicken"}

    monkeypatch.setattr(agent, "stream_reply", fake_stream)

    phone = await agent.reply("u", "dinner ideas", surface="imessage")
    assert phone == "Ideas:\n\n• Salmon\n• Chicken"
    assert await agent.reply("u", "dinner ideas", surface="whatsapp") == phone

    web = await agent.reply("u", "dinner ideas", surface="web")
    assert "**Salmon**" in web and "* **Salmon**" in web
