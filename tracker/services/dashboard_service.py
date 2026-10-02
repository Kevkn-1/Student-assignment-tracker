"""Business logic for the dashboard: turns raw counts into display-ready stats."""
from datetime import date, timedelta

from ..repositories import dashboard_repository as repo
from .assignment_service import PRIORITY_CHOICES, STATUS_CHOICES, due_label

DUE_SOON_DAYS = 7   # "due soon" = today up to and including today + 7 days
LIST_LIMIT = 5      # rows shown in the "due soon" and "overdue" lists
FOCUS_LIMIT = 6     # rows shown in the "Today's focus" list
FOCUS_SOON_DAYS = 2 # focus also covers work due within the next 2 days


def percent(part, whole):
    """Whole-number percentage, rounded half up; 0 when there is nothing."""
    if whole <= 0:
        return 0
    return (part * 100 + whole // 2) // whole


def _with_due_label(rows, today):
    items = []
    for row in rows:
        item = dict(row)
        days_until = (date.fromisoformat(item["deadline"]) - today).days
        item["days_until"] = days_until
        item["due_label"] = due_label(days_until)
        items.append(item)
    return items


def _build_focus(overdue_list, due_soon):
    """Overdue, due-today and very-soon work, most urgent first.

    Built from rows already fetched for the dashboard lists, so this adds no
    extra queries and reuses the existing deadline logic instead of duplicating it.
    """
    focus = []
    for item in overdue_list:
        row = dict(item)
        row["kind"] = "overdue"
        focus.append(row)

    # due_soon is ordered by deadline, so everything past the window can be skipped.
    for item in due_soon:
        if len(focus) >= FOCUS_LIMIT:
            break
        if item["days_until"] > FOCUS_SOON_DAYS:
            break
        row = dict(item)
        row["kind"] = "today" if item["days_until"] == 0 else "soon"
        focus.append(row)
    return focus[:FOCUS_LIMIT]


def get_dashboard(today=None):
    today = today or date.today()
    today_iso = today.isoformat()
    week_end_iso = (today + timedelta(days=DUE_SOON_DAYS)).isoformat()

    # Status breakdown (every status is present, even with 0)
    raw_status = repo.status_counts()
    counts = {value: raw_status.get(value, 0) for value, _ in STATUS_CHOICES}
    total = sum(counts.values())
    completed = counts["completed"]
    open_total = total - completed

    # Open assignments by priority, most urgent first
    raw_priority = repo.open_priority_counts()
    priorities = []
    for value, label in reversed(PRIORITY_CHOICES):  # high, medium, low
        count = raw_priority.get(value, 0)
        priorities.append({
            "value": value, "label": label, "count": count,
            "percent": percent(count, open_total),
        })

    # Per-subject progress
    subjects = []
    for row in repo.subject_breakdown():
        subjects.append({
            "id": row["id"], "name": row["name"], "code": row["code"],
            "total": row["total"], "completed": row["completed"],
            "open": row["total"] - row["completed"],
            "percent": percent(row["completed"], row["total"]),
        })

    # Deadline lists (hoisted so the focus list can reuse them)
    due_soon = _with_due_label(
        repo.due_between(today_iso, week_end_iso, LIST_LIMIT), today
    )
    overdue_list = _with_due_label(repo.overdue(today_iso, LIST_LIMIT), today)

    return {
        "today": today_iso,
        "has_data": total > 0,
        "total": total,
        "open": open_total,
        "counts": counts,
        "status_counts": [
            {"value": value, "label": label, "count": counts[value]}
            for value, label in STATUS_CHOICES
        ],
        "completion_rate": percent(completed, total),
        "overdue": repo.count_overdue(today_iso),
        "due_today": repo.count_due_between(today_iso, today_iso),
        "due_this_week": repo.count_due_between(today_iso, week_end_iso),
        "due_soon_days": DUE_SOON_DAYS,
        "priorities": priorities,
        "subjects": subjects,
        "due_soon": due_soon,
        "overdue_list": overdue_list,
        "focus": _build_focus(overdue_list, due_soon),
    }