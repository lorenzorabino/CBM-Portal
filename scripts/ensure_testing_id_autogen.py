import os
from sqlalchemy import create_engine, text

"""
Ensure CBM_Testing.Testing_ID auto-generates values in SQL Server.
If column is not IDENTITY, attach a SEQUENCE + DEFAULT constraint so inserts
that omit Testing_ID get NEXT VALUE FOR the sequence.

Safe: preserves existing IDs and data; no table rebuild.

Usage (PowerShell):
  $env:MSSQL_CONN = 'mssql+pyodbc://.../CBM2?driver=ODBC+Driver+17+for+SQL+Server'
  .\.venv\Scripts\python.exe .\scripts\ensure_testing_id_autogen.py
"""

SEQUENCE_NAME = 'dbo.CBM_Testing_Seq'
DEFAULT_NAME = 'DF_CBM_Testing_Testing_ID'


def main():
    conn_str = os.environ.get('MSSQL_CONN')
    if not conn_str:
        raise SystemExit('MSSQL_CONN not set')
    eng = create_engine(conn_str, pool_pre_ping=True, future=True)
    with eng.begin() as conn:
        # Check identity property
        is_identity = conn.execute(text(
            "SELECT COLUMNPROPERTY(OBJECT_ID('dbo.CBM_Testing'),'Testing_ID','IsIdentity')"
        )).scalar()
        if is_identity == 1:
            print('CBM_Testing.Testing_ID is already IDENTITY. No action needed.')
            return
        print('CBM_Testing.Testing_ID is NOT IDENTITY. Ensuring SEQUENCE + DEFAULT...')
        # Determine next value
        next_val = conn.execute(text("SELECT COALESCE(MAX(Testing_ID)+1, 1) FROM dbo.CBM_Testing")).scalar() or 1
        # Create sequence if missing or below next_val
        seq_exists = conn.execute(text(
            "SELECT 1 FROM sys.sequences WHERE OBJECT_SCHEMA_NAME(object_id)='dbo' AND name='CBM_Testing_Seq'"
        )).fetchone()
        if not seq_exists:
            conn.execute(text(
                f"CREATE SEQUENCE {SEQUENCE_NAME} START WITH {int(next_val)} INCREMENT BY 1"
            ))
            print(f'Created sequence {SEQUENCE_NAME} starting at {next_val}.')
        else:
            # Advance the sequence to at least next_val
            current_val = conn.execute(text(
                "SELECT CAST(current_value AS BIGINT) FROM sys.sequences WHERE OBJECT_SCHEMA_NAME(object_id)='dbo' AND name='CBM_Testing_Seq'"
            )).scalar()
            if current_val is None or current_val < (next_val - 1):
                # use ALTER SEQUENCE RESTART WITH
                conn.execute(text(
                    f"ALTER SEQUENCE {SEQUENCE_NAME} RESTART WITH {int(next_val)}"
                ))
                print(f'Restarted sequence {SEQUENCE_NAME} at {next_val}.')
        # Check for existing default constraint on Testing_ID
        has_default = conn.execute(text(
            """
            SELECT 1
            FROM sys.default_constraints dc
            JOIN sys.columns c ON c.default_object_id = dc.object_id AND c.object_id = OBJECT_ID('dbo.CBM_Testing')
            WHERE c.name='Testing_ID'
            """
        )).fetchone()
        if not has_default:
            conn.execute(text(
                f"ALTER TABLE dbo.CBM_Testing ADD CONSTRAINT {DEFAULT_NAME} DEFAULT (NEXT VALUE FOR {SEQUENCE_NAME}) FOR Testing_ID"
            ))
            print(f'Added DEFAULT constraint {DEFAULT_NAME} on CBM_Testing.Testing_ID.')
        else:
            print('A DEFAULT constraint for Testing_ID already exists.')
        print('Auto-generation for Testing_ID ensured.')


if __name__ == '__main__':
    main()
