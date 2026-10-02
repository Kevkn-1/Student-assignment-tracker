"""Business logic for subjects: validation and rules.

Views call this module; this module calls the repository. No SQL here.
"""
import re
import sqlite3

from ..repositories import subject_repository as repo
from .errors import ConflictError, NotFoundError, ValidationError

NAME_MAX_LENGTH = 100
CODE_MAX_LENGTH = 20
CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]*$")

DUPLICATE_NAME_MESSAGE = "A subject with this name already exists."


def _validate(raw_name, raw_code):
    """Return (clean_name, clean_code, errors). Never raises."""
    errors = {}

    if not isinstance(raw_name, str):
        raw_name = ""
    name = " ".join(raw_name.split())  # trim + collapse inner whitespace
    if not name:
        errors["name"] = "Subject name is required."
    elif len(name) > NAME_MAX_LENGTH:
        errors["name"] = f"Subject name must be at most {NAME_MAX_LENGTH} characters."
    elif not name.isprintable():
        errors["name"] = "Subject name contains invalid characters."

    if not isinstance(raw_code, str):
        raw_code = ""
    code = raw_code.strip()
    if not code:
        code = None  # the code is optional
    elif len(code) > CODE_MAX_LENGTH:
        errors["code"] = f"Subject code must be at most {CODE_MAX_LENGTH} characters."
    elif not CODE_PATTERN.match(code):
        errors["code"] = (
            "Subject code may only contain letters, digits, spaces, "
            "dashes, underscores and dots."
        )
    else:
        code = code.upper()

    return name, code, errors


def list_subjects():
    return repo.list_all()


def get_subject(subject_id):
    subject = repo.get_by_id(subject_id)
    if subject is None:
        raise NotFoundError("Subject not found.")
    return subject


def create_subject(raw_name, raw_code):
    name, code, errors = _validate(raw_name, raw_code)
    if not errors and repo.find_by_name(name):
        errors["name"] = DUPLICATE_NAME_MESSAGE
    if errors:
        raise ValidationError(errors)
    try:
        return repo.insert(name, code)
    except sqlite3.IntegrityError:
        # Safety net if two requests race past the duplicate check.
        raise ValidationError({"name": DUPLICATE_NAME_MESSAGE})


def update_subject(subject_id, raw_name, raw_code):
    get_subject(subject_id)  # raises NotFoundError if missing
    name, code, errors = _validate(raw_name, raw_code)
    if not errors and repo.find_by_name(name, exclude_id=subject_id):
        errors["name"] = DUPLICATE_NAME_MESSAGE
    if errors:
        raise ValidationError(errors)
    try:
        repo.update(subject_id, name, code)
    except sqlite3.IntegrityError:
        raise ValidationError({"name": DUPLICATE_NAME_MESSAGE})


def delete_subject(subject_id):
    get_subject(subject_id)  # raises NotFoundError if missing
    if repo.count_assignments(subject_id) > 0:
        raise ConflictError(
            "This subject still has assignments. "
            "Delete or move them before deleting the subject."
        )
    repo.delete(subject_id)