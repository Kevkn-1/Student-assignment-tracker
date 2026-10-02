"""Main routes for Student Assignment Tracker."""
from flask import Blueprint, jsonify

from tracker.db import list_tables

bp = Blueprint("main", __name__)


@bp.route("/health")
def health():
    """Setup check: confirms the app runs and the schema was created."""
    return jsonify(status="ok", tables=list_tables())
