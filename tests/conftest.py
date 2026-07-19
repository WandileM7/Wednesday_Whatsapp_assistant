import os
import pathlib

import pytest

# Must be set before any backend import: settings and the db engine are
# created at module load.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_wednesday.db"
os.environ["API_TOKEN"] = ""


@pytest.fixture(autouse=True, scope="session")
def _test_db():
    # Delete only at session boundaries: the engine pools connections, so
    # removing the file mid-session orphans them.
    pathlib.Path("test_wednesday.db").unlink(missing_ok=True)
    yield
    pathlib.Path("test_wednesday.db").unlink(missing_ok=True)
