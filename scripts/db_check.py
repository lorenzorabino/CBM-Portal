import os
import sqlite3

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE_DIR, 'database', 'portal.db')

def rows(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()

def main():
    print('DB path:', DB_PATH)
    con = sqlite3.connect(DB_PATH)
    try:
        print('Tables:')
        for (name,) in rows(con, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            print(' -', name)
        print('\nPlanner sample rows:')
        for r in rows(con, "SELECT id, week_number, year, department, equipment, date, day FROM Planner ORDER BY id DESC LIMIT 5"):
            print(' ', r)
        print('\nPlanner_Test sample rows:')
        for r in rows(con, "SELECT id, planner_id, test_type, test_date, done FROM Planner_Test ORDER BY id DESC LIMIT 10"):
            print(' ', r)
    except sqlite3.OperationalError as e:
        print('SQLite error:', e)
    finally:
        con.close()

if __name__ == '__main__':
    main()
