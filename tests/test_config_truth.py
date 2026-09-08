"""The defaults, .env.example and the README have to agree.

Not pedantry. The quick start is `cp .env.example .env` and the README says the
defaults work out of the box, so .env.example *is* the default for anyone who
follows the instructions — and every place these three disagreed, the
disagreement was a real bug on the default path:

  - VISION_MODEL unset fell back to llava:7b, which no document tells you to
    pull, so the first photo answered "model not found".
  - PIPER_VOICE shipped en_US-lessac-medium while the persona, the style bundle
    and every other default specify a dry British lilt.
  - OLLAMA_MODEL shipped llama3.1:8b while the sampling floor, guard.py's
    fabrication patterns and evals/ were all measured on qwen2.5.

Each was invisible to the rest of the suite, because tests read `settings` and
`settings` reads the developer's own .env — which was correct all along.
"""
import pathlib
import re

import pytest

from backend.config import Settings

REPO = pathlib.Path(__file__).resolve().parent.parent
ENV_EXAMPLE = (REPO / ".env.example").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")

# Settings() would read the developer's .env, which is exactly what hides this
# class of bug. Read the class defaults instead.
DEFAULTS = {name: f.default for name, f in Settings.model_fields.items()}


def _env_example(key: str) -> str | None:
    m = re.search(rf"^{key}=(.*)$", ENV_EXAMPLE, re.M)
    return m.group(1).strip() if m else None


# The settings where a mismatch changes behaviour on a fresh install, rather
# than merely looking untidy.
@pytest.mark.parametrize("key, field", [
    ("OLLAMA_MODEL", "ollama_model"),
    ("OLLAMA_MODEL_UTILITY", "ollama_model_utility"),
    ("PIPER_VOICE", "piper_voice"),
    ("VISION_MODEL", "vision_model"),
    ("EMBED_MODEL", "embed_model"),
    ("WHISPER_MODEL", "whisper_model"),
    ("GROQ_STT_MODEL", "groq_stt_model"),
    ("KOKORO_VOICE", "kokoro_voice"),
    ("DEFAULT_LOCATION", "default_location"),
])
def test_env_example_matches_the_code_default(key, field):
    shipped = _env_example(key)
    if shipped is None:
        pytest.skip(f"{key} is not in .env.example")
    default = DEFAULTS[field]
    # VISION_MODEL is the one deliberate exception: the code default is empty
    # ("pick automatically") while .env.example names the model explicitly so
    # the pull instruction and the config agree. Empty is allowed to be spelt out.
    if default == "":
        return
    assert shipped == default, (
        f"{key}={shipped} in .env.example but the code default is {default!r}. "
        "The quick start copies .env.example, so whichever is wrong is what a "
        "new install actually runs.")


def test_the_readme_names_the_model_the_quick_start_pulls():
    """A default the install instructions never download is a broken install."""
    model = DEFAULTS["ollama_model"]
    assert f"ollama pull {model}" in README, (
        f"the default chat model is {model} but nothing in the README pulls it")
    assert model in _env_example("OLLAMA_MODEL")


def test_every_model_the_readme_tells_you_to_pull_is_used_somewhere():
    """Catches the reverse drift: an instruction to download something that no
    code path ever asks for."""
    pulled = set(re.findall(r"ollama pull ([\w.:-]+)", README))
    referenced = " ".join(str(v) for v in DEFAULTS.values())
    referenced += (REPO / "backend" / "vision.py").read_text(encoding="utf-8")
    for model in pulled:
        assert model in referenced, f"README pulls {model}, nothing uses it"
