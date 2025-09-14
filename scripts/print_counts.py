import os
from sqlalchemy import create_engine, text

conn_str = os.getenv('MSSQL_CONN')
if not conn_str:
    raise SystemExit('MSSQL_CONN not set')

eng = create_engine(conn_str, pool_pre_ping=True, future=True)
with eng.begin() as conn:
    p = conn.execute(text('SELECT COUNT(*) FROM Planner')).scalar()
    t = conn.execute(text('SELECT COUNT(*) FROM CBM_Testing')).scalar()
    print('Planner count:', p)
    print('Testing count:', t)
    rows = conn.execute(text("SELECT TOP 10 id, department, equipment, pm_date, schedule_type FROM Planner ORDER BY id DESC")).fetchall()
    for r in rows:
        print('Planner:', r)
    any_tests = conn.execute(text("SELECT TOP 10 planner_id, Test_Type, Status, Done FROM CBM_Testing ORDER BY Testing_ID DESC")).fetchall()
    for r in any_tests:
        print('Test:', r)
