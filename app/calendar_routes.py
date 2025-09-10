from flask import Blueprint, render_template, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from .models import db  # use your existing db
from sqlalchemy.ext.declarative import declarative_base

calendar_bp = Blueprint("calendar", __name__)

# --- SQLAlchemy setup (reuse existing engine if possible) ---
engine = create_engine(
    "mssql+pyodbc://sa:pmdatascience@172.31.3.40,1433/APC?driver=ODBC+Driver+17+for+SQL+Server"
)
Session = sessionmaker(bind=engine)
Base = declarative_base()

# --- Table definitions (readonly minimal) ---
class MaintenanceSchedule(Base):
    __tablename__ = "maintenance_schedule"
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, nullable=True)
    location_id = db.Column(db.Integer, nullable=True)
    next_pm_date = db.Column(db.DateTime, nullable=False)
    resched_date = db.Column(db.DateTime, nullable=True)
    resched_count = db.Column(db.Integer, default=0)

class Machine(Base):
    __tablename__ = "machines"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)

class Location(Base):
    __tablename__ = "locations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)

# --- Routes ---
@calendar_bp.route("/calendar")
def calendar_view():
    return render_template("calendar.html")

@calendar_bp.route("/calendar/events")
def calendar_events():
    session = Session()

    schedules = session.query(MaintenanceSchedule).all()
    machines = {m.id: m.name for m in session.query(Machine).all()}
    locations = {l.id: l.name for l in session.query(Location).all()}

    events = []
    for s in schedules:
        if s.machine_id:
            title = machines.get(s.machine_id, f"Machine {s.machine_id}")
        elif s.location_id:
            title = locations.get(s.location_id, f"Location {s.location_id}")
        else:
            title = f"Schedule {s.id}"

        start_date = (
            s.resched_date.date() if s.resched_count > 0 and s.resched_date else s.next_pm_date.date()
        )
        start_str = start_date.strftime("%Y-%m-%d")

        events.append({
            "id": s.id,
            "title": title,
            "start": start_str,
            "allDay": True,
        })

    session.close()
    return jsonify(events)
