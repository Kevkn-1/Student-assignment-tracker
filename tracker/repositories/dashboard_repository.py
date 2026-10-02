"""Read-only aggregate queries for the dashboard. All values are parameters."""
from ..db import get_db

_OPEN = "a.status != 'completed'"

_LIST_SELECT = (
    "SELECT a.id, a.title, a.priority, a.status, a.deadline, "
    "       s.name AS subject_name "
    "FROM assignments AS a "
    "JOIN subjects AS s ON s.id = a.subject_id "
)
_LIST_ORDER = (
    "ORDER BY a.deadline ASC, "
    "CASE a.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, a.id ASC "
)


def status_counts():
    """{status: count} for statuses that have at least one assignment."""
    rows = get_db().execute(
        "SELECT status, COUNT(*) AS total FROM assignments GROUP BY status"
    ).fetchall()
    return {row["status"]: row["total"] for row in rows}


def open_priority_counts():
    """{priority: count} for assignments that are not completed."""
    rows = get_db().execute(
        "SELECT a.priority, COUNT(*) AS total FROM assignments AS a "
        f"WHERE {_OPEN} GROUP BY a.priority"
    ).fetchall()
    return {row["priority"]: row["total"] for row in rows}


def count_overdue(today_iso):
    return get_db().execute(
        f"SELECT COUNT(*) AS total FROM assignments AS a WHERE {_OPEN} AND a.deadline < ?",
        (today_iso,),
    ).fetchone()["total"]


def count_due_between(start_iso, end_iso):
    """Unfinished assignments with a deadline from start to end (inclusive)."""
    return get_db().execute(
        f"SELECT COUNT(*) AS total FROM assignments AS a "
        f"WHERE {_OPEN} AND a.deadline BETWEEN ? AND ?",
        (start_iso, end_iso),
    ).fetchone()["total"]


def due_between(start_iso, end_iso, limit):
    return get_db().execute(
        _LIST_SELECT
        + f"WHERE {_OPEN} AND a.deadline BETWEEN ? AND ? "
        + _LIST_ORDER + "LIMIT ?",
        (start_iso, end_iso, limit),
    ).fetchall()


def overdue(today_iso, limit):
    return get_db().execute(
        _LIST_SELECT + f"WHERE {_OPEN} AND a.deadline < ? " + _LIST_ORDER + "LIMIT ?",
        (today_iso, limit),
    ).fetchall()


def subject_breakdown():
    """One row per subject (including empty ones) with total/completed counts."""
    return get_db().execute(
        "SELECT s.id, s.name, s.code, "
        "       COUNT(a.id) AS total, "
        "       COALESCE(SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed "
        "FROM subjects AS s "
        "LEFT JOIN assignments AS a ON a.subject_id = s.id "
        "GROUP BY s.id "
        "ORDER BY normalize(s.name) ASC, s.id ASC"
    ).fetchall()