"""Presentation layer for subjects: routes that render templates."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..services import subject_service
from ..services.errors import ConflictError, NotFoundError, ValidationError

bp = Blueprint("subjects", __name__, url_prefix="/subjects")


@bp.route("/")
def list_subjects():
    return render_template(
        "subjects/list.html", subjects=subject_service.list_subjects()
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = {"name": "", "code": ""}
    errors = {}
    if request.method == "POST":
        form = {
            "name": request.form.get("name", ""),
            "code": request.form.get("code", ""),
        }
        try:
            subject_service.create_subject(form["name"], form["code"])
        except ValidationError as exc:
            errors = exc.errors
        else:
            flash("Subject created.", "success")
            return redirect(url_for("subjects.list_subjects"))
    status = 400 if errors else 200
    return render_template("subjects/form.html", subject=None, form=form, errors=errors), status


@bp.route("/<int:subject_id>/edit", methods=["GET", "POST"])
def edit(subject_id):
    try:
        subject = subject_service.get_subject(subject_id)
    except NotFoundError:
        abort(404)

    form = {"name": subject["name"], "code": subject["code"] or ""}
    errors = {}
    if request.method == "POST":
        form = {
            "name": request.form.get("name", ""),
            "code": request.form.get("code", ""),
        }
        try:
            subject_service.update_subject(subject_id, form["name"], form["code"])
        except ValidationError as exc:
            errors = exc.errors
        else:
            flash("Subject updated.", "success")
            return redirect(url_for("subjects.list_subjects"))
    status = 400 if errors else 200
    return render_template("subjects/form.html", subject=subject, form=form, errors=errors), status


@bp.route("/<int:subject_id>/delete", methods=["POST"])
def delete(subject_id):
    try:
        subject_service.delete_subject(subject_id)
    except NotFoundError:
        abort(404)
    except ConflictError as exc:
        flash(str(exc), "error")
    else:
        flash("Subject deleted.", "success")
    return redirect(url_for("subjects.list_subjects"))