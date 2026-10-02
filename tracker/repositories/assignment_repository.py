"""Data access for assignments. Every query is parameterized."""
from ..db import get_db

_SELECT = (
    "SELECT a.id, a.subject_id, a.title, a.description, a.priority, a.status, "
    "       a.deadline, a.created_at, a.updated_at, "
    "       s.name AS subject_name, s.code AS subject_code "
    "FROM assignments AS a "
    "JOIN subjects AS s ON s.id = a.subject_id "
)

# Open work first (soonest deadline, highest priority), completed work last.
_DEFAULT_ORDER = (
    "ORDER BY CASE a.status WHEN 'completed' THEN 1 ELSE 0 END, "
    "         a.deadline ASC, "
    "         CASE a.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
    "         a.id ASC"
)

_PRIORITY_RANK = "CASE a.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"
_PRIORITY_RANK_REVERSED = "CASE a.priority WHEN 'high' THEN 2 WHEN 'medium' THEN 1 ELSE 0 END"
_STATUS_RANK = "CASE a.status WHEN 'pending' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END"

# Every sort key the service exposes. Keys must match service.SORT_KEYS exactly.
SORT_ORDERS = {
    "default": _DEFAULT_ORDER,
    "deadline_asc": f"ORDER BY a.deadline ASC, {_PRIORITY_RANK}, a.id ASC",
    "deadline_desc": f"ORDER BY a.deadline DESC, {_PRIORITY_RANK}, a.id ASC",
    "priority_desc": f"ORDER BY {_PRIORITY_RANK}, a.deadline ASC, a.id ASC",
    "priority_asc": f"ORDER BY {_PRIORITY_RANK_REVERSED}, a.deadline ASC, a.id ASC",
    "title_asc": "ORDER BY normalize(a.title) ASC, a.id ASC",
    "title_desc": "ORDER BY normalize(a.title) DESC, a.id ASC",
    "subject_asc": "ORDER BY normalize(s.name) ASC, a.deadline ASC, a.id ASC",
    "status_asc": f"ORDER BY {_STATUS_RANK}, a.deadline ASC, a.id ASC",
    "created_desc": "ORDER BY a.created_at DESC, a.id DESC",
}

# Older sort keys still accepted by list_assignments()/list_all().
_ORDER_ALIASES = {"priority": "priority_desc", "title": "title_asc"}


def _order_clause(sort):
    """ORDER BY for a sort key; unknown or hostile keys fall back to default."""
    if isinstance(sort, str):
        sort = _ORDER_ALIASES.get(sort, sort)
    if not isinstance(sort, str) or sort not in SORT_ORDERS:
        return SORT_ORDERS["default"]
    return SORT_ORDERS[sort]


def search(subject_id=None, status=None, priority=None, q=None,
           overdue=False, today_iso=None, sort="default"):
    """Filtered, sorted assignment rows.

    Keyword matching is case- and accent-insensitive and treats SQL
    wildcards (% and _) as literal text, so every value stays a parameter.
    """
    conditions = []
    params = []

    if subject_id is not None:
        conditions.append("a.subject_id = ?")
        params.append(subject_id)
    if status:
        conditions.append("a.status = ?")
        params.append(status)
    if priority:
        conditions.append("a.priority = ?")
        params.append(priority)
    if q:
        conditions.append(
            "(instr(normalize(a.title), normalize(?)) > 0 "
            "OR instr(normalize(a.description), normalize(?)) > 0)"
        )
        params.extend([q, q])
    if overdue:
        if today_iso:
            conditions.append("a.status != 'completed' AND a.deadline < ?")
            params.append(today_iso)
        else:
            conditions.append("a.status != 'completed' AND a.deadline < date('now')")

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"{_SELECT} {where_clause} {_order_clause(sort)}"
    return get_db().execute(query, params).fetchall()


def count():
    """Total assignments, ignoring every filter."""
    return get_db().execute("SELECT COUNT(*) AS total FROM assignments").fetchone()["total"]


def list_all(subject_id=None, status=None, priority=None, sort="default"):
    return search(subject_id=subject_id, status=status, priority=priority, sort=sort)


def get_by_id(assignment_id):
    return get_db().execute(
        _SELECT + "WHERE a.id = ?", (assignment_id,)
    ).fetchone()


def insert(subject_id, title, description, priority, status, deadline):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO assignments "
        "(subject_id, title, description, priority, status, deadline) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (subject_id, title, description, priority, status, deadline),
    )
    db.commit()
    return cursor.lastrowid


def update(assignment_id, subject_id, title, description, priority, status, deadline):
    db = get_db()
    db.execute(
        "UPDATE assignments "
        "SET subject_id = ?, title = ?, description = ?, priority = ?, "
        "    status = ?, deadline = ?, updated_at = datetime('now') "
        "WHERE id = ?",
        (subject_id, title, description, priority, status, deadline, assignment_id),
    )
    db.commit()


def update_status(assignment_id, status):
    db = get_db()
    db.execute(
        "UPDATE assignments SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, assignment_id),
    )
    db.commit()


def delete(assignment_id):
    db = get_db()
    db.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    db.commit()