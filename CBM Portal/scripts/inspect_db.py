import os
import sqlite3
import shutil
import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE_DIR, 'database', 'portal.db')

def backup_db():
    if not os.path.exists(DB_PATH):
        print('Database not found at', DB_PATH)
        return None
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = DB_PATH + f'.bak.{ts}'
    shutil.copy2(DB_PATH, bak)
    return bak

def tables_and_counts(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print('Found tables:', tables)
    for t in tables:
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            cnt = cur.fetchone()[0]
            print(f' - {t}: {cnt} rows')
        except Exception as e:
            print(f' - {t}: count failed ({e})')
    return tables

def sample_rows(conn, table, limit=5):
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT * FROM "{table}" LIMIT {limit}')
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        print(f'\nSample rows from {table} (columns: {cols}):')
        for r in rows:
            print(' ', r)
    except Exception as e:
        print(f'Could not read {table}:', e)

def main():
    print('DB path:', DB_PATH)
    bak = backup_db()
    if bak:
        print('Backup created:', bak)
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        tables = tables_and_counts(conn)
        # show samples for common tables if present
        for t in ['Equipment', 'CBM_Technician', 'CBM_Testing', 'Planner', 'Planner_Test', 'Alarm_Level']:
            if t in tables:
                sample_rows(conn, t, limit=5)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
