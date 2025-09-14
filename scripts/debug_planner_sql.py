import os
from sqlalchemy import create_engine, text

conn_str = os.getenv('MSSQL_CONN')
if not conn_str:
    raise SystemExit('MSSQL_CONN not set')
eng = create_engine(conn_str, pool_pre_ping=True, future=True)
sql = (
    "SELECT p.id, p.week_number, p.year, p.department, p.equipment, p.date, p.day, "
    "p.pm_date, p.schedule_type, "
    "COALESCE(p.tasks_count, (SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id), 0) AS total_tests, "
    "COALESCE((SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id AND TRIM(COALESCE(tt.Status, '')) <> ''), 0) AS status_filled, "
    "COALESCE(p.completed_count, (SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id AND (COALESCE(tt.Done,0)=1 OR LOWER(TRIM(COALESCE(tt.Status,''))) IN ('completed','done'))), 0) AS completed_count, "
    "COALESCE(( SELECT STRING_AGG(tt.Test_Type, ', ') FROM ( SELECT DISTINCT LTRIM(RTRIM(COALESCE(Test_Type,''))) AS Test_Type FROM CBM_Testing WHERE planner_id = p.id AND LTRIM(RTRIM(COALESCE(Test_Type, ''))) <> '' ) tt ), '') AS testing_types "
    "FROM Planner p ORDER BY p.id DESC"
)
with eng.begin() as conn:
    try:
        rows = conn.execute(text(sql)).fetchall()
        print('Rows:', len(rows))
        for r in rows[:5]:
            print(r)
    except Exception as e:
        print('ERROR executing SQL:', e)
