import os
import pathlib

import pytest

# Must be set before any backend import: settings and the db engine are
# created at module load.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_wednesday.db"
os.environ["API_TOKEN"] = ""
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


@pytest.fixture(autouse=True, scope="session")
def _test_db():
    # Delete only at session boundaries: the engine pools connections, so
    # removing the file mid-session orphans them.
    pathlib.Path("test_wednesday.db").unlink(missing_ok=True)
    yield
    pathlib.Path("test_wednesday.db").unlink(missing_ok=True)
