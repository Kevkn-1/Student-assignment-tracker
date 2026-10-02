"""Data access for subjects. Every query is parameterized."""
from ..db import get_db


def list_all():
    """All subjects with the number of assignments each one has."""
    return get_db().execute(
        "SELECT s.id, s.name, s.code, s.created_at, "
        "       COUNT(a.id) AS assignment_count "
        "FROM subjects AS s "
        "LEFT JOIN assignments AS a ON a.subject_id = s.id "
        "GROUP BY s.id "
        "ORDER BY s.name COLLATE NOCASE"
    ).fetchall()


def get_by_id(subject_id):
    return get_db().execute(
        "SELECT id, name, code, created_at FROM subjects WHERE id = ?",
        (subject_id,),
    ).fetchone()


def find_by_name(name, exclude_id=None):
    """Find a subject by name (case-insensitive: the column uses NOCASE)."""
    return get_db().execute(
        "SELECT id FROM subjects WHERE name = ? AND (? IS NULL OR id != ?)",
        (name, exclude_id, exclude_id),
    ).fetchone()


def insert(name, code):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO subjects (name, code) VALUES (?, ?)", (name, code)
    )
    db.commit()
    return cursor.lastrowid


def update(subject_id, name, code):
    db = get_db()
    db.execute(
        "UPDATE subjects SET name = ?, code = ? WHERE id = ?",
        (name, code, subject_id),
    )
    db.commit()


def delete(subject_id):
    db = get_db()
    db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    db.commit()


def count_assignments(subject_id):
    row = get_db().execute(
        "SELECT COUNT(*) AS total FROM assignments WHERE subject_id = ?",
        (subject_id,),
    ).fetchone()
    return row["total"]