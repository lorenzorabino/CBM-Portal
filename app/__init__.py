from flask import Flask
from flask import render_template
from .models import db
from flask import session
from .nav_access import NAV_ACCESS
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

    # Database setup: MSSQL required
    mssql_conn = os.environ.get('MSSQL_CONN')
    if not mssql_conn:
        raise RuntimeError("MSSQL_CONN is required. Set a valid SQL Server connection string (pyodbc URL).")
    # Nudge developers to use CBM2, not CBM
    try:
        if '://'+'' in mssql_conn and (mssql_conn.rstrip().split('/')[-1].split('?')[0].upper() == 'CBM'):
            # Visible console warning only; app still runs.
            print("[WARN] MSSQL_CONN points to 'CBM'. Please switch to 'CBM2'.", flush=True)
    except Exception:
        pass
    app.config['SQLALCHEMY_DATABASE_URI'] = mssql_conn
    # Helpful for long-lived connections against SQL Server
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your_secret_key_here'

    # Initialize db
    db.init_app(app)

    # No runtime DDL: schema should be created in SQL Server via migration scripts

    # Register blueprints
    app.register_blueprint(main)
    app.register_blueprint(technician)
    app.register_blueprint(calendar_bp)

    # Error handlers
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template('403.html'), 403

    # Template helper: can_view('link_key') -> bool based on role
    @app.context_processor
    def inject_nav_helpers():
        def can_view(key: str) -> bool:
            try:
                utype = None
                u = session.get('user')
                if isinstance(u, dict):
                    utype = (u.get('user_type') or '').strip().lower()
                if not utype:
                    utype = (session.get('user_type') or '').strip().lower()
                if not utype:
                    utype = 'guest'
                allowed = NAV_ACCESS.get(key, [])
                return (utype in allowed) or ('guest' in allowed and utype == 'guest')
            except Exception:
                return False
        return dict(can_view=can_view)

    return app
