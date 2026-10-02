"""Student Assignment Tracker - application factory."""
from flask import Flask

from config import Config


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    from . import db

    db.init_app(app)
    with app.app_context():
        db.init_db()  # automatic, idempotent database initialization

    from .views.assignments import bp as assignments_bp
    from .views.main import bp as main_bp
    from .views.subjects import bp as subjects_bp
    from .views.dashboard import bp as dashboard_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(subjects_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(assignments_bp)
    return app
    