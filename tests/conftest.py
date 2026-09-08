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
# Pin the chat backend to local for the whole suite. Settings read the real
# .env, so a developer with a hosted key configured would otherwise send the
# Ollama-shaped fixtures down the OpenAI path and fail everywhere. Tests that
# exercise the hosted backend opt in explicitly (see tests/test_llm_router.py).
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""
# Same reasoning: a cap set in the developer's .env would silently change which
# tools every agent test sees. Tests that exercise capping set it themselves.
os.environ["MAX_TOOLS_PER_REQUEST"] = "0"
# And the same again for intent routing, which also narrows the offered set.
os.environ["ROUTE_TOOLS"] = "false"

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
