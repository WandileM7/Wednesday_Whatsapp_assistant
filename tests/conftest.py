import os
import pathlib

import pytest

# Must be set before any backend import: settings and the db engine are
# created at module load.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_wednesday.db"
os.environ["API_TOKEN"] = ""
os.environ["VECTOR_DB_PATH"] = "./test_wednesday-vectors.db"
# Off by default so the suite behaves the same whether or not Ollama is running
# locally — otherwise memory.relevant quietly starts returning real semantic
# results and the lexical-path assertions drift. test_vecstore turns it on with
# a fake embedder, which keeps that file hermetic too.
os.environ["ENABLE_MEMORY_EMBEDDINGS"] = "false"

_DB_FILES = ("test_wednesday.db", "test_wednesday-vectors.db")


@pytest.fixture(autouse=True, scope="session")
def _test_db():
    # Delete only at session boundaries: the engine pools connections, so
    # removing the file mid-session orphans them.
    for name in _DB_FILES:
        for path in pathlib.Path(".").glob(f"{name}*"):   # plus -wal/-shm
            path.unlink(missing_ok=True)
    # Create the schema once, the same way the app does at startup. Without it
    # any test touching a table the app creates lazily fails on "no such table"
    # depending on which other tests happened to run first.
    import asyncio

    from backend import db
    asyncio.run(db.init())
    yield
    for name in _DB_FILES:
        for path in pathlib.Path(".").glob(f"{name}*"):
            path.unlink(missing_ok=True)
