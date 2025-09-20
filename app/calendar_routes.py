# app/calendar_routes.py

from flask import Blueprint, render_template, jsonify
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

calendar_bp = Blueprint("calendar", __name__)

# --- SQLAlchemy setup (APC DB only) ---
apc_conn = os.getenv("APC_CONN")
if not apc_conn:
    raise RuntimeError("APC_CONN is missing from environment (.env)")

engine = create_engine(apc_conn, pool_pre_ping=True)
Session = sessionmaker(bind=engine)
Base = declarative_base()

# --- Table definitions (APC DB) ---
class MaintenanceSchedule(Base):
    __tablename__ = "maintenance_schedule"
    id = Column(Integer, primary_key=True)
    machine_id = Column(Integer, nullable=True)
    location_id = Column(Integer, nullable=True)
    next_pm_date = Column(DateTime, nullable=False)
    resched_date = Column(DateTime, nullable=True)
    resched_count = Column(Integer, default=0)

class Machine(Base):
    __tablename__ = "machines"
    id = Column(Integer, primary_key=True)
    name = Column(String)

class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True)
    name = Column(String)

# --- Routes ---
@calendar_bp.route("/calendar")
def calendar_view():
    return render_template("calendar.html")

@calendar_bp.route("/calendar/events")
def calendar_events():
    with Session() as session:
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
                s.resched_date.date()
                if s.resched_count > 0 and s.resched_date
                else s.next_pm_date.date()
            )
            start_str = start_date.strftime("%Y-%m-%d")

            events.append({
                "id": s.id,
                "title": title,
                "start": start_str,
                "allDay": True,
            })

        return jsonify(events)
