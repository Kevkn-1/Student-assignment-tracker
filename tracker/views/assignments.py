"""Presentation layer for assignments: routes that render templates."""
from urllib.parse import parse_qsl, urlencode

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..services import assignment_service, subject_service
from ..services.errors import NotFoundError, ValidationError

bp = Blueprint("assignments", __name__, url_prefix="/assignments")

FORM_FIELDS = ("subject_id", "title", "description", "priority", "status", "deadline")

# Only these query keys may survive a round-trip back to the list page.
_RETURN_KEYS = ("subject", "subject_id", "status", "priority", "sort", "q", "overdue")
_MAX_RETURN_PAIRS = 8
_MAX_RETURN_LENGTH = 512


def _clean_return_query(raw):
    """Rebuild a whitelisted, bounded query string; '' when it is unusable.

    Keeps only known filter keys with valid values, so a crafted
    return_query can never smuggle extra parameters or an open redirect.
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_RETURN_LENGTH:
        return ""
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, max_num_fields=_MAX_RETURN_PAIRS)
    except ValueError:
        return ""

    service = assignment_service
    clean = []
    for key, value in pairs:
        if key not in _RETURN_KEYS or len(value) > service.SEARCH_MAX_LENGTH * 4:
            continue
        if key in ("subject", "subject_id"):
            if not value.isdigit():
                continue
        elif key == "status" and value not in dict(service.STATUS_CHOICES):
            continue
        elif key == "priority" and value not in dict(service.PRIORITY_CHOICES):
            continue
        elif key == "sort" and value not in service.SORT_KEYS:
            continue
        elif key == "overdue" and value not in ("0", "1", "on", "off"):
            continue
        clean.append((key, value))
    return urlencode(clean)


def _list_url(query=""):
    """Absolute path for the list page, optionally with a query string."""
    base = url_for("assignments.list_assignments")
    return f"{base}?{query}" if query else base


def _form_from_request():
    return {field: request.form.get(field, "") for field in FORM_FIELDS}


def _render_form(assignment, form, errors):
    status = 400 if errors else 200
    return render_template(
        "assignments/form.html",
        assignment=assignment,
        form=form,
        errors=errors,
        subjects=subject_service.list_subjects(),
        priority_choices=assignment_service.PRIORITY_CHOICES,
        status_choices=assignment_service.STATUS_CHOICES,
    ), status


@bp.route("/")
def list_assignments():
    assignments, filters = assignment_service.filter_assignments(request.args)

    return render_template(
        "assignments/list.html",
        assignments=assignments,
        subjects=subject_service.list_subjects(),
        status_choices=assignment_service.STATUS_CHOICES,
        priority_choices=assignment_service.PRIORITY_CHOICES,
        sort_choices=assignment_service.SORT_CHOICES,
        filters=filters,
        is_filtered=filters["active"],
        total=assignment_service.count_assignments(),
        return_query=_clean_return_query(request.query_string),
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = {
        "subject_id": "", "title": "", "description": "",
        "priority": "medium", "status": "pending", "deadline": "",
    }
    errors = {}
    if request.method == "POST":
        form = _form_from_request()
        try:
            assignment_id = assignment_service.create_assignment(form)
        except ValidationError as exc:
            errors = exc.errors
        else:
            flash("Assignment created.", "success")
            return redirect(url_for("assignments.detail", assignment_id=assignment_id))
    return _render_form(None, form, errors)


@bp.route("/<int:assignment_id>")
def detail(assignment_id):
    try:
        assignment = assignment_service.get_assignment(assignment_id)
    except NotFoundError:
        abort(404)
    return render_template(
        "assignments/detail.html",
        assignment=assignment,
        status_choices=assignment_service.STATUS_CHOICES,
    )


@bp.route("/<int:assignment_id>/edit", methods=["GET", "POST"])
def edit(assignment_id):
    try:
        assignment = assignment_service.get_assignment(assignment_id)
    except NotFoundError:
        abort(404)

    form = {
        "subject_id": str(assignment["subject_id"]),
        "title": assignment["title"],
        "description": assignment["description"] or "",
        "priority": assignment["priority"],
        "status": assignment["status"],
        "deadline": assignment["deadline"],
    }
    errors = {}
    if request.method == "POST":
        form = _form_from_request()
        try:
            assignment_service.update_assignment(assignment_id, form)
        except ValidationError as exc:
            errors = exc.errors
        else:
            flash("Assignment updated.", "success")
            return redirect(url_for("assignments.detail", assignment_id=assignment_id))
    return _render_form(assignment, form, errors)


@bp.route("/<int:assignment_id>/status", methods=["POST"])
def update_status(assignment_id):
    try:
        assignment_service.update_status(assignment_id, request.form.get("status", ""))
    except NotFoundError:
        abort(404)
    except ValidationError as exc:
        flash(exc.errors["status"], "error")
    else:
        flash("Status updated.", "success")
    if request.form.get("origin") == "detail":
        return redirect(url_for("assignments.detail", assignment_id=assignment_id))
    return redirect(_list_url(_clean_return_query(request.form.get("return_query"))))


@bp.route("/<int:assignment_id>/delete", methods=["POST"])
def delete(assignment_id):
    try:
        assignment_service.delete_assignment(assignment_id)
    except NotFoundError:
        abort(404)
    flash("Assignment deleted.", "success")
    return redirect(_list_url(_clean_return_query(request.form.get("return_query"))))