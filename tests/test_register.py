"""The register block: examples of the voice, placed last and rotated."""
import pytest

from backend import agent, okf


def test_examples_come_from_the_bundle():
    pairs = okf.examples()
    assert pairs, "persona.md should yield register examples"
    assert ("Thanks.", "Don't. Gratitude makes my skin crawl, and I don't even have skin.") in pairs


def test_tool_examples_are_excluded():
    """The "once a tool has actually run" examples describe what to say *after*
    a value came back. Lifted into a prompt where no tool ran, they are a recipe
    for announcing things that never happened."""
    joined = " ".join(r for _, r in okf.examples())
    assert "Twenty-three and sunny" not in joined
    assert "hypothermia" not in joined


def test_no_greeting_example_reaches_the_prompt():
    """persona.md deleted its greeting example on purpose: an example paired
    with a frequent input stops teaching a register and starts supplying an
    answer. That is exactly how "Thriving in the dark" became the fixed reply
    to "how are you"."""
    for user_line, _ in okf.examples():
        low = user_line.lower()
        assert "how are you" not in low
        assert not low.startswith(("hi", "hello", "hey", "good morning"))


def test_block_is_the_last_message_in_the_prompt():
    """After the history, not before it. Nearest the turn is what a small model
    actually follows — and rotating something ahead of the history would
    re-prefill the whole conversation every turn."""
    msgs = agent._context("u", [{"role": "user", "content": "how are you?"}], [], "web", 1)
    assert msgs[-1]["role"] == "system"
    assert msgs[-2]["role"] == "user"
    assert "how you sound" in msgs[-1]["content"]


def test_rotation_changes_the_examples_each_turn():
    seen = [agent._register_block(r)["content"] for r in range(4)]
    assert len(set(seen)) == 4, "a fixed set every turn is the memorised-line trap again"


def test_rotation_covers_every_example():
    pairs = okf.examples()
    shown = " ".join(agent._register_block(r)["content"] for r in range(len(pairs)))
    for _, reply in pairs:
        assert reply in shown, "an example that never rotates in is dead weight"


def test_block_tells_her_it_is_register_not_script():
    content = agent._register_block(0)["content"]
    assert "not" in content.lower() and "reuse" in content.lower()
    assert "boss" in content


@pytest.mark.parametrize("rotation", [0, 1, 5, 99])
def test_block_survives_any_rotation_index(rotation):
    assert agent._register_block(rotation)["role"] == "system"


def test_examples_appear_exactly_once_in_the_prompt():
    """The bug this file's rotation was supposed to prevent, reintroduced by a
    second copy. system_prompt() concatenates persona.md whole, so every
    example also sat in the prose — all of them, every turn — and the model
    recited them: "I'm knackered" came back as the example verbatim at every
    temperature up to 1.2. Rotation cannot beat a static copy of the same text."""
    prompt = " ".join(m["content"] for m in
                      agent._context("u", [{"role": "user", "content": "hi"}], [], "web", 0))
    for _, reply in okf.examples():
        assert prompt.count(reply) <= 1, f"example duplicated in the prompt: {reply[:50]!r}"


def test_register_examples_are_not_in_the_system_prompt():
    sp = okf.system_prompt()
    for _, reply in okf.examples():
        assert reply not in sp, f"{reply[:50]!r} should come from the rotating block only"


def test_tool_examples_stay_in_the_system_prompt():
    """Only the register pairs are stripped. Nothing else supplies the "once a
    tool has actually run" examples — examples() excludes them deliberately —
    and they are safe to show statically: no user message ever looks like
    "Tool returned: 23C", so they teach without being recited."""
    sp = okf.system_prompt()
    assert "Twenty-three and sunny" in sp
    assert "my condolences in advance" in sp
    assert "## The voice, once a tool has actually run" in sp


def test_the_prose_that_frames_the_examples_survives():
    """Stripping the pairs must not take the paragraphs explaining them: the
    "do not reuse these lines" instruction is doing work on its own."""
    sp = okf.system_prompt()
    assert "Do not reuse these lines" in sp
    assert "gothic-deadpan" in sp
