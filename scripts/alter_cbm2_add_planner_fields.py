import os
from sqlalchemy import create_engine, text

"""
Alter CBM2: add denormalized Planner fields to CBM_Testing and backfill.

Adds columns (if missing):
- planner_week_number INT NULL
- planner_year INT NULL
- planner_department NVARCHAR(255) NULL
- planner_equipment NVARCHAR(255) NULL
- planner_pm_date NVARCHAR(50) NULL
- planner_schedule_type NVARCHAR(100) NULL

Then backfills values from Planner for rows that have planner_id.

Usage (PowerShell):
  $env:MSSQL_CONN = 'mssql+pyodbc://.../CBM2?driver=ODBC+Driver+17+for+SQL+Server'
  .\.venv\Scripts\python.exe .\scripts\alter_cbm2_add_planner_fields.py
"""

ALTERS = [
    (
        "planner_week_number",
        "INT",
        "ALTER TABLE dbo.CBM_Testing ADD planner_week_number INT NULL;",
    ),
    (
        "planner_year",
        "INT",
        "ALTER TABLE dbo.CBM_Testing ADD planner_year INT NULL;",
    ),
    (
        "planner_department",
        "NVARCHAR(255)",
        "ALTER TABLE dbo.CBM_Testing ADD planner_department NVARCHAR(255) NULL;",
    ),
    (
        "planner_equipment",
        "NVARCHAR(255)",
        "ALTER TABLE dbo.CBM_Testing ADD planner_equipment NVARCHAR(255) NULL;",
    ),
    (
        "planner_pm_date",
        "NVARCHAR(50)",
        "ALTER TABLE dbo.CBM_Testing ADD planner_pm_date NVARCHAR(50) NULL;",
    ),
    (
        "planner_schedule_type",
        "NVARCHAR(100)",
        "ALTER TABLE dbo.CBM_Testing ADD planner_schedule_type NVARCHAR(100) NULL;",
    ),
]


def ensure_columns(conn):
    for col, typ, ddl in ALTERS:
        exists = conn.execute(text(
            """
            SELECT 1
            FROM sys.columns c
            WHERE c.object_id = OBJECT_ID('dbo.CBM_Testing')
              AND c.name = :col
            """
        ), {"col": col}).fetchone()
        if not exists:
            conn.execute(text(ddl))
            print(f"Added column: {col} {typ}")
        else:
            print(f"Column exists: {col}")


def backfill(conn):
    # Backfill from Planner where planner_id is present
    upd = text(
        """
        UPDATE t
        SET t.planner_week_number = p.week_number,
            t.planner_year = p.year,
            t.planner_department = p.department,
            t.planner_equipment = p.equipment,
            t.planner_pm_date = p.pm_date,
            t.planner_schedule_type = p.schedule_type
        FROM dbo.CBM_Testing t
        JOIN dbo.Planner p ON p.id = t.planner_id
        WHERE (
            t.planner_week_number IS NULL OR
            t.planner_year IS NULL OR
            t.planner_department IS NULL OR
            t.planner_equipment IS NULL OR
            t.planner_pm_date IS NULL OR
            t.planner_schedule_type IS NULL
        )
        """
    )
    res = conn.execute(upd)
    try:
        cnt = res.rowcount
    except Exception:
        cnt = None
    print(f"Backfill updated rows: {cnt if cnt is not None else '?'}")


def main():
    conn_str = os.environ.get('MSSQL_CONN')
    if not conn_str:
        raise RuntimeError('MSSQL_CONN not set. Point it to CBM2.')
    eng = create_engine(conn_str, pool_pre_ping=True, future=True)
    with eng.begin() as conn:
        ensure_columns(conn)
        backfill(conn)
    print('Alter and backfill completed.')


if __name__ == '__main__':
    main()
