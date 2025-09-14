import os
from sqlalchemy import create_engine, text

"""
Backfill CBM_Testing rows from Planner rows that have no tests yet.
- For each Planner p with zero CBM_Testing rows, insert tests based on:
  1) If p.schedule_type matches a known type, create a single test of that type.
  2) Else, create one test per type from a default set.
- Equipment is resolved/created by Planner.equipment and Planner.department.

Usage (PowerShell):
  $env:MSSQL_CONN = 'mssql+pyodbc://...'; .\.venv\Scripts\python.exe .\scripts\sync_planner_to_testing.py

Env:
  MSSQL_CONN must be set.
"""

DEFAULT_TYPES = [
    'Vibration Analysis',
    'Oil Analysis',
    'Thermal Imaging',
    'Ultrasonic Analysis',
    'Motor Dynamic Analysis',
    'Ultrasonic Leak Detection',
    'Dynamic Balancing',
    'Other',
]

# Map some common schedule_type values to a single testing type
SCHEDULE_TO_TYPE = {
    'validation': 'Validation',
    'va': 'Vibration Analysis',
    'vibration': 'Vibration Analysis',
    'oa': 'Oil Analysis',
    'oil': 'Oil Analysis',
    'thermal': 'Thermal Imaging',
    'ti': 'Thermal Imaging',
    'ultrasonic': 'Ultrasonic Analysis',
    'ua': 'Ultrasonic Analysis',
    'dma': 'Motor Dynamic Analysis',
    'mda': 'Motor Dynamic Analysis',
    'motor dynamic': 'Motor Dynamic Analysis',
    'leak detection': 'Ultrasonic Leak Detection',
    'uld': 'Ultrasonic Leak Detection',
    'balancing': 'Dynamic Balancing',
    'db': 'Dynamic Balancing',
}


def get_engine():
    conn = os.environ.get('MSSQL_CONN')
    if not conn:
        raise RuntimeError('MSSQL_CONN not set')
    return create_engine(conn, pool_pre_ping=True, future=True)


def ensure_equipment(conn, department: str, equipment: str) -> int | None:
    if not equipment:
        return None
    row = conn.execute(text(
        "SELECT TOP 1 EquipmentID FROM Equipment WHERE CAST(Machine AS NVARCHAR(255)) = :m"
    ), {"m": equipment}).fetchone()
    if row:
        return int(row[0])
    if not department:
        department = 'General'
    conn.execute(text(
        "INSERT INTO Equipment (Department, Machine, Status) VALUES (:d, :m, 'Active')"
    ), {"d": department, "m": equipment})
    rid = conn.execute(text("SELECT CAST(SCOPE_IDENTITY() AS INT)"))
    rid = rid.scalar()
    return int(rid) if rid is not None else None


def choose_types(schedule_type: str | None) -> list[str]:
    if not schedule_type:
        return DEFAULT_TYPES
    key = str(schedule_type).strip().lower()
    t = SCHEDULE_TO_TYPE.get(key)
    if t:
        return [t]
    # If schedule_type already one of the default types (case-insensitive)
    for d in DEFAULT_TYPES:
        if key == d.lower():
            return [d]
    return DEFAULT_TYPES


def main():
    eng = get_engine()
    total_planners = 0
    total_tests = 0
    with eng.begin() as conn:
        # Find planners without any tests
        res = conn.execute(text(
            """
            SELECT p.id, p.department, p.equipment, p.date, p.day, p.pm_date, p.schedule_type
            FROM Planner p
            WHERE NOT EXISTS (SELECT 1 FROM CBM_Testing t WHERE t.planner_id = p.id)
            ORDER BY p.id ASC
            """
        ))
        for pid, dept, equip, pdate, day, pm_date, sched in res.fetchall():
            total_planners += 1
            equipment_id = ensure_equipment(conn, dept or '', equip or '')
            # pick a date for Test_Date, prefer p.date then pm_date
            tdate = pdate or pm_date
            # Decide testing types
            types = choose_types(sched)
            for tt in types:
                conn.execute(text(
                    """
                    INSERT INTO CBM_Testing (CBM_Technician_ID, Equipment_ID, Test_Date, Result, planner_id, Test_Type, Done)
                    VALUES (NULL, :equipment_id, :test_date, NULL, :planner_id, :test_type, 0)
                    """
                ), {"equipment_id": equipment_id, "test_date": tdate, "planner_id": pid, "test_type": tt})
                total_tests += 1
    print(f"Backfill complete. Planners processed: {total_planners}, tests inserted: {total_tests}")


if __name__ == '__main__':
    main()
