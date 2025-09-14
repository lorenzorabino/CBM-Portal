import os
from sqlalchemy import create_engine, text

"""
Add tasks_count and completed_count columns to dbo.Planner in CBM2 (if missing)
and backfill their values based on CBM_Testing rows.

Usage (PowerShell):
  $env:MSSQL_CONN = 'mssql+pyodbc://.../CBM2?driver=ODBC+Driver+17+for+SQL+Server'
  .\.venv\Scripts\python.exe .\scripts\alter_cbm2_add_counts.py
"""

def main():
    conn_str = os.environ.get('MSSQL_CONN')
    if not conn_str:
        raise RuntimeError('MSSQL_CONN not set')
    if conn_str.rsplit('/', 1)[-1].split('?', 1)[0].upper() != 'CBM2':
        print('[WARN] This script is intended for CBM2. Proceeding anyway...')
    eng = create_engine(conn_str, pool_pre_ping=True, future=True)
    with eng.begin() as conn:
        # Add columns if missing
        for col, typ in (('tasks_count','INT'), ('completed_count','INT')):
            ddl = f"""
            IF NOT EXISTS (
                SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.Planner') AND name = '{col}'
            )
            BEGIN
                ALTER TABLE dbo.Planner ADD {col} {typ} NULL;
            END
            """
            conn.execute(text(ddl))
        # Backfill counts from CBM_Testing
        # tasks_count = total tests for planner
        # completed_count = Done=1 OR Status in ('completed','done')
        upd_total = conn.execute(text(
            """
            UPDATE p
            SET tasks_count = x.total
            FROM dbo.Planner p
            CROSS APPLY (
              SELECT COUNT(*) AS total FROM dbo.CBM_Testing t WHERE t.planner_id = p.id
            ) x
            """
        ))
        upd_completed = conn.execute(text(
            """
            UPDATE p
            SET completed_count = x.completed
            FROM dbo.Planner p
            CROSS APPLY (
              SELECT COUNT(*) AS completed
              FROM dbo.CBM_Testing t
              WHERE t.planner_id = p.id
                AND (COALESCE(t.Done,0)=1 OR LOWER(LTRIM(RTRIM(COALESCE(t.Status,'')))) IN ('completed','done'))
            ) x
            """
        ))
    print('Alter/backfill of Planner.tasks_count and completed_count completed.')

if __name__ == '__main__':
    main()
