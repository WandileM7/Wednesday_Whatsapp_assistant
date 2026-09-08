"""Local document Q&A: chunking, BM25 passage ranking, mtime reindexing.

Runs against a tmp folder pointed at by settings.documents_dir — never the
user's real notes.
"""
import pytest

from backend import documents
from backend.config import settings


@pytest.fixture
def docs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    documents._cache = None          # the index is process-global
    yield tmp_path
    documents._cache = None


def test_no_folder_returns_a_helpful_message(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path / "nope"))
    documents._cache = None
    out = documents.search("anything")
    assert isinstance(out, str) and "No documents indexed" in out
    documents._cache = None


def test_indexes_supported_files_and_skips_others(docs_dir):
    (docs_dir / "lease.md").write_text("Rent is due on the first of each month.")
    (docs_dir / "notes.txt").write_text("The wifi password is hunter2.")
    (docs_dir / "photo.png").write_bytes(b"\x89PNG binary")
    sources = {p["source"] for p in documents.index()}
    assert sources == {"lease.md", "notes.txt"}


def test_finds_the_right_passage(docs_dir):
    (docs_dir / "lease.md").write_text("Rent is due on the first of each month.")
    (docs_dir / "notes.txt").write_text("The wifi password is hunter2.")
    hits = documents.search("wifi password")
    assert hits[0]["source"] == "notes.txt"
    assert "hunter2" in hits[0]["text"]


def test_no_match_says_so(docs_dir):
    (docs_dir / "lease.md").write_text("Rent is due on the first.")
    assert documents.search("submarine") == "Nothing in your documents matches that."


def test_long_file_is_split_into_passages(docs_dir):
    # paragraphs well past the chunk size must produce multiple passages
    paras = "\n\n".join(f"Paragraph {i} " + "filler " * 40 for i in range(6))
    (docs_dir / "long.md").write_text(paras)
    chunks = [p for p in documents.index() if p["source"] == "long.md"]
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 1200 for c in chunks)  # ~_CHUNK_CHARS + one para


def test_search_returns_the_passage_not_the_whole_file(docs_dir):
    paras = "\n\n".join([
        "Chapter one is about gardening and soil.",
        "filler " * 200,
        "The escape hatch code is 9981.",
    ])
    (docs_dir / "manual.md").write_text(paras)
    hits = documents.search("escape hatch code", limit=1)
    assert "9981" in hits[0]["text"]
    assert "gardening" not in hits[0]["text"]  # unrelated chapter didn't come along


def test_reindexes_when_a_file_changes(docs_dir):
    import os
    f = docs_dir / "note.md"
    f.write_text("The codeword is falcon.")
    assert "falcon" in documents.search("codeword")[0]["text"]
    f.write_text("The codeword is osprey.")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))  # force a new mtime
    assert "osprey" in documents.search("codeword")[0]["text"]


def test_switching_folders_reindexes(monkeypatch, tmp_path):
    """Pointing documents_dir at a different folder picks up its contents."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    monkeypatch.setattr(settings, "documents_dir", str(a))
    documents._cache = None
    assert documents.index() == []
    (b / "note.md").write_text("The codeword is falcon.")
    monkeypatch.setattr(settings, "documents_dir", str(b))
    assert "falcon" in documents.search("codeword")[0]["text"]
    documents._cache = None


def test_subfolders_are_indexed_with_relative_source(docs_dir):
    (docs_dir / "work").mkdir()
    (docs_dir / "work" / "review.md").write_text("Performance review is in March.")
    hits = documents.search("performance review")
    assert hits[0]["source"] == "work/review.md".replace("/", __import__("os").sep)
