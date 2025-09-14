import os
from sqlalchemy import create_engine, text

def main():
    conn_str = os.getenv('MSSQL_CONN')
    if not conn_str:
        print('[test_mssql] MSSQL_CONN not set. Set the environment variable and re-run.')
        return
    print('[test_mssql] Using connection:', conn_str)
    try:
        # crude check of DB name
        db_name = conn_str.rsplit('/', 1)[-1].split('?', 1)[0]
        if db_name.upper() == 'CBM':
            print('[test_mssql][WARN] Connection points to CBM (legacy). Use CBM2 instead.')
    except Exception:
        pass
    try:
        engine = create_engine(conn_str, pool_pre_ping=True)
        with engine.begin() as conn:
            # Try a lightweight metadata query; works in SQL Server
            ver = conn.execute(text('SELECT @@VERSION')).scalar()
            print('[test_mssql] Connected to SQL Server:')
            print(ver)
            # List a few user tables if available
            try:
                rows = conn.execute(text("SELECT TOP 10 TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"))
                print('[test_mssql] Sample tables:')
                for r in rows:
                    print(' -', f"{r[0]}.{r[1]}")
            except Exception as e:
                print('[test_mssql] Could not list tables:', e)
    except Exception as e:
        print('[test_mssql] Connection failed:', e)

if __name__ == '__main__':
    main()
