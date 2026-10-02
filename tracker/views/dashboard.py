"""Home page: the assignment dashboard with statistics."""
from flask import Blueprint, render_template

from tracker.services import dashboard_service

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    return render_template("dashboard/dashboard.html", stats=dashboard_service.get_dashboard())

