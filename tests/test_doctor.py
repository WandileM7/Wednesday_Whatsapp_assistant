"""/doctor should surface the silent config footguns as advisory warnings:
the utility-model cache-eviction trap and a default token-encryption secret."""
import backend.main as main
from backend.config import settings


def _warns(monkeypatch, **overrides):
    for k, v in overrides.items():
        monkeypatch.setattr(settings, k, v)
    return main._config_warnings(overrides.pop("_pulled", ["llama3.1:8b", "llama3.2:3b"]))


def test_warns_when_utility_model_unset(monkeypatch):
    warns = _warns(monkeypatch, ollama_model_utility="", session_secret="strong-secret")
    assert any("OLLAMA_MODEL_UTILITY is unset" in w for w in warns)


def test_warns_when_utility_equals_chat_model(monkeypatch):
    warns = _warns(monkeypatch, ollama_model="llama3.1:8b",
                   ollama_model_utility="llama3.1:8b", session_secret="strong-secret")
    assert any("equals OLLAMA_MODEL" in w for w in warns)


def test_warns_when_utility_model_not_pulled(monkeypatch):
    monkeypatch.setattr(settings, "ollama_model", "llama3.1:8b")
    monkeypatch.setattr(settings, "ollama_model_utility", "phi3:mini")
    monkeypatch.setattr(settings, "session_secret", "strong-secret")
    warns = main._config_warnings(["llama3.1:8b", "llama3.2:3b"])
    assert any("phi3:mini not pulled" in w for w in warns)


def test_warns_on_default_session_secret(monkeypatch):
    monkeypatch.setattr(settings, "ollama_model_utility", "llama3.2:3b")
    monkeypatch.setattr(settings, "ollama_model", "llama3.1:8b")
    monkeypatch.setattr(settings, "session_secret", "change-me-in-production")
    warns = main._config_warnings(["llama3.1:8b", "llama3.2:3b"])
    assert any("SESSION_SECRET is the default" in w for w in warns)


def test_clean_config_has_no_warnings(monkeypatch):
    monkeypatch.setattr(settings, "ollama_model", "llama3.1:8b")
    monkeypatch.setattr(settings, "ollama_model_utility", "llama3.2:3b")
    monkeypatch.setattr(settings, "session_secret", "a-real-unique-secret")
    assert main._config_warnings(["llama3.1:8b", "llama3.2:3b"]) == []
