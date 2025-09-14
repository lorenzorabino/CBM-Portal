import os
import sys
from sqlalchemy import create_engine, text

CONN = os.environ.get('MSSQL_CONN')
if not CONN:
    print('MSSQL_CONN not set', file=sys.stderr)
    sys.exit(1)

e = create_engine(CONN, pool_pre_ping=True)
with e.begin() as conn:
    # Add created_at if missing
    conn.execute(text(
        """
        IF NOT EXISTS (
          SELECT 1 FROM sys.columns 
          WHERE object_id = OBJECT_ID('dbo.Planner') 
            AND name = 'created_at'
        )
        BEGIN
          ALTER TABLE dbo.Planner ADD created_at DATETIME2 NOT NULL CONSTRAINT DF_Planner_created_at DEFAULT (SYSUTCDATETIME());
        END
        """
    ))
    # Add row_uid (GUID) if missing
    conn.execute(text(
        """
        IF NOT EXISTS (
          SELECT 1 FROM sys.columns 
          WHERE object_id = OBJECT_ID('dbo.Planner') 
            AND name = 'row_uid'
        )
        BEGIN
          ALTER TABLE dbo.Planner ADD row_uid UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_Planner_row_uid DEFAULT NEWID();
        END
        """
    ))
print('Alter complete: created_at, row_uid ensured on Planner.')
