import pathlib

import pytest

from backend import db, skills
from backend.config import settings


@pytest.fixture()
def skills_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "okf_dir", str(tmp_path))
    monkeypatch.setattr(skills, "_cache", None)
    d = tmp_path / "skills"; d.mkdir()
    (d / "brew.md").write_text(
        "---\nname: brew\ndescription: Make coffee properly\n---\n\nGrind. Pour. Wait.\n")
    (d / "broken.md").write_text("no frontmatter here")
    return d


def test_catalog_parses_and_skips_broken(skills_dir):
    cat = skills.catalog()
    assert [s["name"] for s in cat] == ["brew"]
    assert "brew: Make coffee properly" in skills.catalog_lines()


def test_body_returns_content_and_bumps_usage(skills_dir):
    assert skills.body("brew") == "Grind. Pour. Wait."
    assert skills.body("brew") is not None
    assert skills._load_usage() == {"brew": 2}
    assert skills.body("nope") is None


def test_propose_writes_reviewable_draft(skills_dir):
    path = skills.propose("Weekly Report!", "Summarise the week", "Do the thing.")
    assert path.parent.name == "proposals"
    parsed = skills._parse(path)
    assert parsed["name"] == "weekly-report"
    # proposals are not active skills
    assert all(s["name"] != "weekly-report" for s in skills.catalog())


def test_curator_report_flags_unused_and_proposals(skills_dir):
    skills.propose("draft-idea", "An idea", "Body")
    report = skills.curator_report()
    assert "brew: used 0x" in report
    assert "never used" in report and "brew" in report
    assert "draft-idea.md" in report


def test_curator_report_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "okf_dir", str(tmp_path))
    monkeypatch.setattr(skills, "_cache", None)
    assert skills.curator_report() is None


async def test_oauth_tokens_encrypted_at_rest():
    import datetime as dt
    from sqlalchemy import select
    await db.init()
    await db.save_token("testsvc", "secret-access", "secret-refresh",
                        dt.datetime.now() + dt.timedelta(hours=1))
    token = await db.get_token("testsvc")
    assert token.access_token == "secret-access"
    assert token.refresh_token == "secret-refresh"
    # raw row must not contain the plaintext
    async with db.SessionLocal() as s:
        raw = (await s.execute(select(db.OAuthToken)
                               .where(db.OAuthToken.service == "testsvc"))).scalar_one()
        assert raw.access_token != "secret-access"
        assert "secret" not in raw.access_token
