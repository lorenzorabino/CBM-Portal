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


def clean_all():
    if not os.path.exists(DB_PATH):
        print('Database not found at', DB_PATH)
        return
    bak = backup_db()
    if bak:
        print('Backup created:', bak)

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        # list tables excluding sqlite internal tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall() if not r[0].startswith('sqlite_')]
        print('Tables to clean:', tables)

        # disable foreign keys for mass deletes
        try:
            cur.execute('PRAGMA foreign_keys=OFF')
        except Exception:
            pass

        for t in tables:
            try:
                cur.execute(f'DELETE FROM "{t}"')
                print(f'Cleared: {t}')
            except Exception as e:
                print(f'Failed to clear {t}:', e)
        conn.commit()

        # reset sqlite_sequence so AUTOINCREMENT counters go back to 0
        try:
            cur.execute("DELETE FROM sqlite_sequence")
            print('Reset sqlite_sequence')
        except Exception as e:
            print('Could not reset sqlite_sequence:', e)
        conn.commit()

        try:
            cur.execute('PRAGMA foreign_keys=ON')
        except Exception:
            pass

        # reclaim space
        try:
            cur.execute('VACUUM')
            print('VACUUM complete')
        except Exception as e:
            print('VACUUM failed:', e)
    finally:
        conn.close()


if __name__ == '__main__':
    print('Cleaning all data from', DB_PATH)
    clean_all()
