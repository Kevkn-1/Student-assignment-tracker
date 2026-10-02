"""Business logic for assignments: validation and rules.

Views call this module; this module calls the repositories. No SQL here.
"""
import re
import sqlite3
from datetime import date

from ..repositories import assignment_repository as repo
from ..repositories import subject_repository
from .errors import NotFoundError, ValidationError

TITLE_MAX_LENGTH = 150
DESCRIPTION_MAX_LENGTH = 2000
MIN_YEAR = 2000
MAX_YEAR = 2100

PRIORITY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High")]
STATUS_CHOICES = [
    ("pending", "Pending"),
    ("in_progress", "In progress"),
    ("completed", "Completed"),
]
PRIORITIES = {value for value, _ in PRIORITY_CHOICES}
STATUSES = {value for value, _ in STATUS_CHOICES}

SEARCH_MAX_LENGTH = 100  # longest keyword kept after trimming

SORT_CHOICES = [
    ("default", "Default (Open first, soonest deadline)"),
    ("deadline_asc", "Deadline (Soonest first)"),
    ("deadline_desc", "Deadline (Furthest first)"),
    ("priority_desc", "Priority (High to low)"),
    ("priority_asc", "Priority (Low to high)"),
    ("title_asc", "Title (A to Z)"),
    ("title_desc", "Title (Z to A)"),
    ("subject_asc", "Subject (A to Z)"),
    ("status_asc", "Status (Open first)"),
    ("created_desc", "Newest first"),
]
# Must match repository.SORT_ORDERS exactly (asserted by the test suite).
SORT_KEYS = set(repo.SORT_ORDERS)
# Sort keys accepted by the older list_assignments() API, aliases included.
SORTS = SORT_KEYS | {"priority", "title"}

_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ID_PATTERN = re.compile(r"[0-9]{1,18}")

# Query-string values that mean "yes" for the overdue checkbox.
_OVERDUE_TRUE = {"1", "on", "true", "yes"}

STATUS_ERROR = "Status must be pending, in progress or completed."
SUBJECT_MISSING_ERROR = "Selected subject does not exist."


def _text(raw, key):
    value = raw.get(key)
    return value if isinstance(value, str) else ""


def _validate(raw):
    """Return (clean_values, errors). Never raises."""
    errors = {}
    clean = {}

    # Subject
    subject_raw = _text(raw, "subject_id").strip()
    if not subject_raw:
        errors["subject_id"] = "Please choose a subject."
    elif not _ID_PATTERN.fullmatch(subject_raw):
        errors["subject_id"] = "Invalid subject."
    else:
        subject_id = int(subject_raw)
        if subject_repository.get_by_id(subject_id) is None:
            errors["subject_id"] = SUBJECT_MISSING_ERROR
        else:
            clean["subject_id"] = subject_id

    # Title
    title = " ".join(_text(raw, "title").split())
    if not title:
        errors["title"] = "Title is required."
    elif len(title) > TITLE_MAX_LENGTH:
        errors["title"] = f"Title must be at most {TITLE_MAX_LENGTH} characters."
    elif not title.isprintable():
        errors["title"] = "Title contains invalid characters."
    else:
        clean["title"] = title

    # Description (optional; newlines allowed)
    description = _text(raw, "description").replace("\r\n", "\n").strip()
    if not description:
        clean["description"] = None
    elif len(description) > DESCRIPTION_MAX_LENGTH:
        errors["description"] = (
            f"Description must be at most {DESCRIPTION_MAX_LENGTH} characters."
        )
    elif not all(ch.isprintable() or ch in "\n\t" for ch in description):
        errors["description"] = "Description contains invalid characters."
    else:
        clean["description"] = description

    # Priority and status
    priority = _text(raw, "priority").strip()
    if priority in PRIORITIES:
        clean["priority"] = priority
    else:
        errors["priority"] = "Priority must be low, medium or high."

    status = _text(raw, "status").strip()
    if status in STATUSES:
        clean["status"] = status
    else:
        errors["status"] = STATUS_ERROR

    # Deadline: strict YYYY-MM-DD, real calendar date, sensible year
    deadline_raw = _text(raw, "deadline").strip()
    if not deadline_raw:
        errors["deadline"] = "Deadline is required."
    else:
        parsed = None
        if _DATE_PATTERN.fullmatch(deadline_raw):
            try:
                parsed = date(
                    int(deadline_raw[0:4]), int(deadline_raw[5:7]), int(deadline_raw[8:10])
                )
            except ValueError:
                parsed = None
        if parsed is None:
            errors["deadline"] = "Deadline must be a valid date (YYYY-MM-DD)."
        elif not MIN_YEAR <= parsed.year <= MAX_YEAR:
            errors["deadline"] = f"Deadline year must be between {MIN_YEAR} and {MAX_YEAR}."
        else:
            clean["deadline"] = parsed.isoformat()

    return clean, errors


def _present(row, today):
    """Turn a database row into a dict and add the computed 'overdue' flag."""
    assignment = dict(row)
    assignment["overdue"] = (
        assignment["status"] != "completed"
        and assignment["deadline"] < today.isoformat()
    )
    return assignment


def list_assignments(today=None, subject_id=None, status=None, priority=None, sort="default"):
    today = today or date.today()

    clean_subject_id = None
    if subject_id:
        try:
            clean_subject_id = int(str(subject_id).strip())
        except (ValueError, TypeError):
            clean_subject_id = None

    clean_status = status.strip() if isinstance(status, str) else None
    if clean_status not in STATUSES:
        clean_status = None

    clean_priority = priority.strip() if isinstance(priority, str) else None
    if clean_priority not in PRIORITIES:
        clean_priority = None

    clean_sort = sort.strip() if isinstance(sort, str) else "default"
    if clean_sort not in SORTS:
        clean_sort = "default"

    rows = repo.list_all(
        subject_id=clean_subject_id,
        status=clean_status,
        priority=clean_priority,
        sort=clean_sort,
    )
    return [_present(row, today) for row in rows]


def count_assignments(*_args, **_kwargs):
    """Total number of assignments. Filter arguments are ignored on purpose."""
    return repo.count()


def _text_from(raw, *keys):
    """First non-empty string among keys, stripped; '' when there is none."""
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
    return ""


def parse_filters(raw):
    """Turn untrusted query params into a clean, display-ready filter dict.

    Anything unknown, malformed or out of range falls back to its neutral
    value, so junk input can never reach SQL or change the page layout.
    """
    raw = raw or {}

    # Subject: must be a short digit string that names a real subject.
    subject_raw = _text_from(raw, "subject", "subject_id")
    subject_id = None
    if _ID_PATTERN.fullmatch(subject_raw):
        candidate = int(subject_raw)
        if subject_repository.get_by_id(candidate) is not None:
            subject_id = candidate

    status = _text_from(raw, "status")
    if status not in STATUSES:
        status = ""

    priority = _text_from(raw, "priority")
    if priority not in PRIORITIES:
        priority = ""

    sort = _text_from(raw, "sort")
    if sort not in SORT_KEYS:
        sort = "default"

    # Keyword: trimmed, whitespace collapsed, printable, length capped.
    q = raw.get("q")
    if isinstance(q, str):
        q = " ".join(q.split())
        if not q.isprintable():
            q = ""
        q = q[:SEARCH_MAX_LENGTH]
    else:
        q = ""

    overdue_raw = raw.get("overdue")
    overdue = isinstance(overdue_raw, str) and overdue_raw.strip().lower() in _OVERDUE_TRUE

    filters = {
        "subject_id": subject_id,
        "status": status,
        "priority": priority,
        "q": q,
        "overdue": overdue,
        "sort": sort,
    }
    filters["active"] = bool(
        subject_id is not None or status or priority or q or overdue or sort != "default"
    )
    return filters


def filter_assignments(raw, today=None):
    """Return (assignments, filters) for untrusted query params."""
    today = today or date.today()
    filters = parse_filters(raw)
    rows = repo.search(
        subject_id=filters["subject_id"],
        status=filters["status"] or None,
        priority=filters["priority"] or None,
        q=filters["q"] or None,
        overdue=filters["overdue"],
        today_iso=today.isoformat(),
        sort=filters["sort"],
    )
    return [_present(row, today) for row in rows], filters


def get_assignment(assignment_id, today=None):
    row = repo.get_by_id(assignment_id)
    if row is None:
        raise NotFoundError("Assignment not found.")
    return _present(row, today or date.today())


def create_assignment(raw):
    clean, errors = _validate(raw)
    if errors:
        raise ValidationError(errors)
    try:
        return repo.insert(
            clean["subject_id"], clean["title"], clean["description"],
            clean["priority"], clean["status"], clean["deadline"],
        )
    except sqlite3.IntegrityError:
        # Safety net: the subject was deleted right after validation.
        raise ValidationError({"subject_id": SUBJECT_MISSING_ERROR})


def update_assignment(assignment_id, raw):
    get_assignment(assignment_id)  # raises NotFoundError if missing
    clean, errors = _validate(raw)
    if errors:
        raise ValidationError(errors)
    try:
        repo.update(
            assignment_id, clean["subject_id"], clean["title"], clean["description"],
            clean["priority"], clean["status"], clean["deadline"],
        )
    except sqlite3.IntegrityError:
        raise ValidationError({"subject_id": SUBJECT_MISSING_ERROR})


def update_status(assignment_id, raw_status):
    get_assignment(assignment_id)  # raises NotFoundError if missing
    status = raw_status.strip() if isinstance(raw_status, str) else ""
    if status not in STATUSES:
        raise ValidationError({"status": STATUS_ERROR})
    repo.update_status(assignment_id, status)


def delete_assignment(assignment_id):
    get_assignment(assignment_id)  # raises NotFoundError if missing
    repo.delete(assignment_id)