"""Database access layer: connection handling and schema initialization.

Only low-level SQLite concerns live here. Queries for subjects/assignments
will go in tracker/repositories/ and always use parameterized SQL.
"""
import os
import sqlite3
import unicodedata
from pathlib import Path

import click
from flask import current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _normalize(value):
    """Case-, accent- and whitespace-insensitive key for search and sorting.

    Registered as the SQL function ``normalize()`` so that keyword matching
    and alphabetical ORDER BY treat "Étude" and "etude" as the same text.
    """
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.split()).casefold()


def get_db():
    """Return the per-request SQLite connection (created on first use)."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        # SQLite does not enforce foreign keys unless enabled per connection.
        g.db.execute("PRAGMA foreign_keys = ON")
        # SQL used by the dashboard calls normalize(); SQLite has no such
        # built-in, so register it as a Python scalar function.
        g.db.create_function("normalize", 1, _normalize)
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(reset=False):
    """Create the database file and tables if they do not exist.

    Safe to call on every start-up (schema uses IF NOT EXISTS).
    With reset=True all existing data is dropped first.
    """
    os.makedirs(os.path.dirname(current_app.config["DATABASE"]) or ".", exist_ok=True)
    db = get_db()
    if reset:
        db.executescript(
            "DROP TABLE IF EXISTS assignments; DROP TABLE IF EXISTS subjects;"
        )
    db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.commit()


def list_tables():
    """Names of the application tables currently in the database."""
    rows = get_db().execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row["name"] for row in rows]


@click.command("init-db")
@click.option("--reset", is_flag=True, help="Drop existing tables (deletes all data).")
def init_db_command(reset):
    """Initialize the database (`flask --app app init-db [--reset]`)."""
    init_db(reset=reset)
    click.echo("Database reset and initialized." if reset else "Database initialized.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)