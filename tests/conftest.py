import os

# Must be set before any backend import: settings and the db engine are
# created at module load.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_wednesday.db"
os.environ["API_TOKEN"] = ""
