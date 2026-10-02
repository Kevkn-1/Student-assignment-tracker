"""Business logic for the dashboard: turns raw counts into display-ready stats."""
from datetime import date, timedelta

from ..repositories import dashboard_repository as repo
from .assignment_service import PRIORITY_CHOICES, STATUS_CHOICES

DUE_SOON_DAYS = 7   # "due soon" = today up to and including today + 7 days
LIST_LIMIT = 5      # rows shown in the "due soon" and "overdue" lists


def percent(part, whole):
    """Whole-number percentage, rounded half up; 0 when there is nothing."""
    if whole <= 0:
        return 0
    return (part * 100 + whole // 2) // whole


def due_label(days_until):
    """Human wording for the distance to a deadline (negative = overdue)."""
    if days_until < 0:
        days = -days_until
        return f"{days} day{'' if days == 1 else 's'} overdue"
    if days_until == 0:
        return "Due today"
    if days_until == 1:
        return "Due tomorrow"
    return f"In {days_until} days"


def _with_due_label(rows, today):
    items = []
    for row in rows:
        item = dict(row)
        days_until = (date.fromisoformat(item["deadline"]) - today).days
        item["days_until"] = days_until
        item["due_label"] = due_label(days_until)
        items.append(item)
    return items


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
        "due_soon": _with_due_label(
            repo.due_between(today_iso, week_end_iso, LIST_LIMIT), today
        ),
        "overdue_list": _with_due_label(repo.overdue(today_iso, LIST_LIMIT), today),
    }