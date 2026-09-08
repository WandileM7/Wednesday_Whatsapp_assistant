from email.message import EmailMessage

import pytest

from backend import email_channel
from backend.config import settings


@pytest.fixture()
def email_settings(monkeypatch):
    monkeypatch.setattr(settings, "email_address", "wednesday@example.com")
    monkeypatch.setattr(settings, "email_password", "app-pass")
    monkeypatch.setattr(settings, "email_allowed_senders",
                        "wandile@example.com, friend@example.com")


def test_disabled_without_creds(monkeypatch):
    monkeypatch.setattr(settings, "email_address", "")
    assert not email_channel.enabled()


def test_owner_maps_to_default_user(email_settings):
    assert email_channel.user_key_for("wandile@example.com") == settings.default_user
    assert email_channel.user_key_for("WANDILE@example.com") == settings.default_user
    assert email_channel.user_key_for("friend@example.com") == "mail:friend@example.com"
    assert email_channel.user_key_for("stranger@example.com") is None


def test_empty_allowlist_answers_nobody(email_settings, monkeypatch):
    monkeypatch.setattr(settings, "email_allowed_senders", "")
    assert email_channel.user_key_for("wandile@example.com") is None


def test_extract_text_plain_and_multipart():
    plain = EmailMessage()
    plain.set_content("hello wednesday")
    assert email_channel.extract_text(plain).strip() == "hello wednesday"

    multi = EmailMessage()
    multi.set_content("plain part")
    multi.add_alternative("<p>html part</p>", subtype="html")
    assert "plain part" in email_channel.extract_text(multi)
    assert "html" not in email_channel.extract_text(multi)
