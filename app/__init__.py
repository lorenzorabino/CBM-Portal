from flask import Flask
from .models import db
from .routes import main
from .technician_routes import technician
from .calendar_routes import calendar_bp
import os

def create_app():
    # Base directory = simple-web-portal/
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Tell Flask where to find static (outside app) and templates (inside app)
    app = Flask(
        __name__,
        static_folder=os.path.join(base_dir, "static"),
        template_folder=os.path.join(os.path.dirname(__file__), "templates")
    )

    # Database setup
    db_path = os.path.join(base_dir, 'database', 'portal_demo3.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your_secret_key_here'

    # Initialize db
    db.init_app(app)

    # Ensure attachments table exists
    with app.app_context():
        try:
            from sqlalchemy import text
            with db.engine.begin() as conn:
                conn.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS Testing_Attachments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        testing_id INTEGER NOT NULL,
                        file_name TEXT NOT NULL,
                        original_name TEXT,
                        mime_type TEXT,
                        size INTEGER,
                        uploaded_at TEXT DEFAULT (datetime('now')),
                        equipment_id INTEGER,
                        test_type TEXT
                    )
                    """
                ))
        except Exception:
            # Non-fatal if creation fails; routes will handle gracefully
            pass

    # Register blueprints
    app.register_blueprint(main)
    app.register_blueprint(technician)
    app.register_blueprint(calendar_bp)

    return app
