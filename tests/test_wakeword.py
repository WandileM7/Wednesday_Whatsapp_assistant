"""Wake-word gating: only ambient audio is gated, mishearings still count, and
deliberate input is never held hostage to saying her name."""
import pytest

from backend import wakeword
from backend.config import settings


@pytest.fixture
def required(monkeypatch):
    monkeypatch.setattr(settings, "wake_word_required", True)
    monkeypatch.setattr(settings, "wake_word", "wednesday")


# ---- split ------------------------------------------------------------------

def test_strips_the_name_and_keeps_the_request():
    assert wakeword.split("Wednesday, what's the weather?") == (True, "what's the weather?")


def test_accepts_a_greeting_prefix():
    assert wakeword.split("hey Wednesday turn the lights off") == (
        True, "turn the lights off")
    assert wakeword.split("ok Wednesday, play something") == (True, "play something")


@pytest.mark.parametrize("heard", [
    "Wednesdays, what's the time",      # whisper pluralises it
    "when's day what's the time",       # and mangles it entirely
    "Wensday, what's the time",
    "wednesday's what's the time",
])
def test_accepts_common_mishearings(heard):
    addressed, rest = wakeword.split(heard)
    assert addressed is True
    assert "what's the time" in rest


def test_unaddressed_speech_is_not_matched():
    assert wakeword.split("so then I told him it was fine") == (
        False, "so then I told him it was fine")


def test_name_mid_sentence_does_not_count():
    # she's being talked *about*, not *to*
    addressed, _ = wakeword.split("I'll ask Wednesday about it later")
    assert addressed is False


def test_bare_name_is_addressed_with_empty_remainder():
    assert wakeword.split("Wednesday?") == (True, "")


def test_empty_input():
    assert wakeword.split("") == (False, "")
    assert wakeword.split("   ") == (False, "")


def test_case_and_punctuation_insensitive():
    assert wakeword.split("  WEDNESDAY -- lights on") == (True, "lights on")


def test_a_custom_wake_word_is_honoured(monkeypatch):
    monkeypatch.setattr(settings, "wake_word", "jarvis")
    assert wakeword.split("Jarvis, status report") == (True, "status report")


# ---- gate -------------------------------------------------------------------

def test_gate_is_off_by_default():
    # nothing changes for existing setups
    assert settings.wake_word_required is False
    assert wakeword.gate("turn the lights on", hands_free=True) == (
        True, "turn the lights on")


def test_gate_ignores_unaddressed_ambient_speech(required):
    addressed, _ = wakeword.gate("did you watch the game last night", hands_free=True)
    assert addressed is False


def test_gate_passes_addressed_ambient_speech(required):
    assert wakeword.gate("Wednesday, lights off", hands_free=True) == (True, "lights off")


def test_deliberate_input_is_never_gated(required):
    """Press-to-talk or typing is plainly addressed to her — demanding the name
    there would just be rude."""
    assert wakeword.gate("lights off", hands_free=False) == (True, "lights off")
