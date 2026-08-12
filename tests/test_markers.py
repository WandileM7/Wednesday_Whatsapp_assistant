"""Speech-marker stripping — the model emits capitalised and invented tags
that must never reach the chat or the TTS, while markdown links and numeric
citations must survive. Regression guard for the [Hiss]/[Sighing] leak."""
from backend import markers


def test_strips_lowercase_allowed_tag():
    assert markers.strip("[sighing] Fine.") == "Fine."
    assert markers.strip("[break] pause") == "pause"


def test_strips_capitalised_tag():
    # the model doesn't honour the lowercase rule
    assert markers.strip("[Sighing] Fine.") == "Fine."


def test_strips_invented_tag():
    assert markers.strip("[Hiss] Contracts befit a lawyer.") == "Contracts befit a lawyer."


def test_keeps_markdown_link():
    # a marker never precedes "(", so links survive
    assert markers.strip("See [the docs](http://x)") == "See [the docs](http://x)"


def test_keeps_numeric_citations():
    # citations start with a digit, so they aren't markers
    assert markers.strip("Per source [1] and [12].") == "Per source [1] and [12]."


def test_strip_is_idempotent_and_leaves_plain_text():
    assert markers.strip("nothing to strip here") == "nothing to strip here"
    assert markers.strip(markers.strip("[calm] ok")) == "ok"


def test_safe_len_holds_back_a_half_received_marker():
    # while streaming, don't split mid-marker
    assert markers.safe_len("Hello [sigh") == len("Hello ")
    # a complete marker (or no bracket) streams fully
    assert markers.safe_len("Hello [sighing] there") == len("Hello [sighing] there")
    assert markers.safe_len("no brackets at all") == len("no brackets at all")


# ---- reply-mode requests -----------------------------------------------------
# "Use text now please" was answered "Got it. I'll be sending replies as plain
# text from now on", with no tool call, nothing stored, and the next reply
# delivered as a voice note anyway. Resolving it here takes the decision away
# from the model's tool choice.
import pytest

from backend.markers import reply_mode_request


@pytest.mark.parametrize("text", [
    "Use text now please", "use text", "reply with text", "text me only",
    "switch to text", "send written replies", "stop sending voice notes",
    "no more voice notes", "stop the audio", "respond in writing",
])
def test_asks_for_text(text):
    assert reply_mode_request(text) == "text"


@pytest.mark.parametrize("text", [
    "use voice", "send voice notes", "reply with audio",
    "switch to voice", "speak aloud", "voice from now on", "stop texting",
])
def test_asks_for_voice(text):
    assert reply_mode_request(text) == "voice"


@pytest.mark.parametrize("text", [
    "play eternity", "what's on my calendar?", "send that email",
    "how are you?", "read me the news",
    # Talking *about* a voice note is not asking for one.
    "did you get my text?",
    # Too vague to act on. Guessing here would silently change the channel on a
    # turn that never asked, which is worse than leaving the setting alone.
    "talk to me",
])
def test_leaves_ordinary_turns_alone(text):
    assert reply_mode_request(text) is None


def test_strips_content_bearing_pseudo_marker():
    """Real capture: the model hid the answer in a fake tag. An apostrophe used
    to dodge the letters-only pattern, so it leaked into chat and the TTS."""
    assert markers.strip("[it's seventeen seventeen] Eleven minutes past five.") \
        == "Eleven minutes past five."
    assert markers.strip("[time is 17:17] Five seventeen.") == "Five seventeen."


def test_still_keeps_links_and_citations_with_the_wider_pattern():
    assert markers.strip("See [the docs](http://x)") == "See [the docs](http://x)"
    assert markers.strip("Per [1] and [12].") == "Per [1] and [12]."
def test_still_keeps_links_and_citations_with_the_wider_pattern():
    assert markers.strip("See [the docs](http://x)") == "See [the docs](http://x)"
    assert markers.strip("Per [1] and [12].") == "Per [1] and [12]."
