import os
import sys
from sqlalchemy import create_engine, text

"""
Add a foreign key from CBM_Testing.planner_id to Planner.id in SQL Server.
- Cleans up orphaned planner_id values (sets to NULL when Planner row missing)
- Creates a supporting index if missing
- Adds FK constraint if missing

Requires env var MSSQL_CONN (SQLAlchemy URL, e.g. mssql+pyodbc://...)
"""

FK_NAME = 'FK_CBM_Testing_Planner'
IDX_NAME = 'IX_CBM_Testing_planner_id'


def get_engine():
    conn = os.environ.get('MSSQL_CONN')
    if not conn:
        print('ERROR: MSSQL_CONN environment variable is not set.', file=sys.stderr)
        sys.exit(2)
    try:
        engine = create_engine(conn, pool_pre_ping=True, future=True)
        # quick connect test
        with engine.connect() as _:
            pass
        return engine
    except Exception as e:
        print(f'ERROR: Failed to connect to SQL Server with MSSQL_CONN. {e}', file=sys.stderr)
        sys.exit(2)


def get_column_type(conn, table_name, column_name):
    row = conn.execute(text(
        """
        SELECT DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = :t AND COLUMN_NAME = :c
        """
    ), {"t": table_name, "c": column_name}).fetchone()
    return row[0] if row else None


def fk_exists(conn):
    row = conn.execute(text(
        """
        SELECT 1
        FROM sys.foreign_keys fk
        JOIN sys.tables t ON t.object_id = fk.parent_object_id
        WHERE fk.name = :fkname AND t.name = 'CBM_Testing'
        """
    ), {"fkname": FK_NAME}).fetchone()
    return bool(row)


def index_exists(conn):
    row = conn.execute(text(
        """
        SELECT 1
        FROM sys.indexes i
        JOIN sys.tables t ON t.object_id = i.object_id
        WHERE i.name = :idx AND t.name = 'CBM_Testing'
        """
    ), {"idx": IDX_NAME}).fetchone()
    return bool(row)


def count_orphans(conn):
    return conn.execute(text(
        """
        SELECT COUNT(*)
        FROM CBM_Testing ct
        WHERE ct.planner_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM Planner p WHERE p.id = ct.planner_id)
        """
    )).scalar() or 0


def main():
    engine = get_engine()
    with engine.begin() as conn:
        # Types report
        pid_type = get_column_type(conn, 'Planner', 'id')
        ct_pid_type = get_column_type(conn, 'CBM_Testing', 'planner_id')
        print(f"Planner.id type: {pid_type}; CBM_Testing.planner_id type: {ct_pid_type}")

        # Orphan cleanup
        orphans = count_orphans(conn)
        if orphans:
            print(f"Found {orphans} CBM_Testing rows with orphaned planner_id. Setting to NULL...")
            conn.execute(text(
                """
                UPDATE CBM_Testing
                SET planner_id = NULL
                WHERE planner_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM Planner p WHERE p.id = CBM_Testing.planner_id)
                """
            ))
        else:
            print("No orphaned planner_id rows found.")

        # Index
        if not index_exists(conn):
            print(f"Creating index {IDX_NAME} on CBM_Testing(planner_id)...")
            conn.execute(text(f"CREATE INDEX {IDX_NAME} ON CBM_Testing(planner_id)"))
        else:
            print(f"Index {IDX_NAME} already exists.")

        # FK
        if fk_exists(conn):
            print(f"Foreign key {FK_NAME} already exists. Nothing to do.")
            return

        # Validate data types are compatible (int/bigint). Otherwise, abort with note.
        compatible_types = {('int', 'int'), ('bigint', 'bigint'), ('bigint', 'int'), ('int', 'bigint')}
        if (pid_type, ct_pid_type) not in compatible_types:
            print("ERROR: Incompatible column types for FK: Planner.id (", pid_type,
                  ") vs CBM_Testing.planner_id (", ct_pid_type, ").\n"
                  "Please align types (e.g., ALTER COLUMN) and re-run.", sep='')
            sys.exit(1)

        # Add FK (NO ACTION by default). To cascade deletes of a Planner into CBM_Testing, change to 'ON DELETE CASCADE'.
        print(f"Adding foreign key {FK_NAME} CBM_Testing(planner_id) -> Planner(id)...")
        conn.execute(text(
            f"""
            ALTER TABLE CBM_Testing WITH CHECK
            ADD CONSTRAINT {FK_NAME}
            FOREIGN KEY (planner_id)
            REFERENCES Planner(id)
            -- ON DELETE CASCADE   -- optionally enable this
            ON UPDATE NO ACTION
            """
        ))
        conn.execute(text(f"ALTER TABLE CBM_Testing CHECK CONSTRAINT {FK_NAME}"))
        print("Foreign key added successfully.")


if __name__ == '__main__':
    main()
