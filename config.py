"""Application configuration."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    # SQLite file location; created automatically on first start.
    DATABASE = os.environ.get(
        "DATABASE_PATH", os.path.join(BASE_DIR, "instance", "tracker.sqlite3")
    )