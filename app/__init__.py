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

    return app
