import os
from sqlalchemy import create_engine, text

"""
Create core schema in the target SQL Server database (point MSSQL_CONN to CBM2).
Tables: Equipment, Planner, CBM_Technician, CBM_Testing, CBM_Testing_Attachments, Alarm_Level
Adds FKs and helpful indexes if missing.

Usage (PowerShell):
  $env:MSSQL_CONN = 'mssql+pyodbc://.../CBM2?driver=ODBC+Driver+17+for+SQL+Server'
  .\.venv\Scripts\python.exe .\scripts\create_schema_mssql.py
"""

DDL_STATEMENTS = [
    # Equipment
    (
        "equipment_table",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'Equipment')
        BEGIN
            CREATE TABLE dbo.Equipment (
                EquipmentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                Department NVARCHAR(255) NOT NULL,
                Machine NVARCHAR(255) NOT NULL,
                Status NVARCHAR(50) NULL
            );
        END
        """
    ),
    # Planner
    (
        "planner_table",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'Planner')
        BEGIN
            CREATE TABLE dbo.Planner (
                id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                week_number INT NULL,
                year INT NULL,
                department NVARCHAR(255) NULL,
                equipment NVARCHAR(255) NULL,
                date NVARCHAR(50) NULL,
                day NVARCHAR(20) NULL,
                pm_date NVARCHAR(50) NULL,
                schedule_type NVARCHAR(100) NULL,
                proposed_target_date NVARCHAR(50) NULL,
                tasks_count INT NULL,
                completed_count INT NULL
            );
        END
        """
    ),
    # CBM_Technician
    (
        "tech_table",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'CBM_Technician')
        BEGIN
            CREATE TABLE dbo.CBM_Technician (
                CBM_ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                Name NVARCHAR(255) NOT NULL,
                Expertise NVARCHAR(255) NULL,
                Email NVARCHAR(255) NULL
            );
        END
        """
    ),
    # CBM_Testing
    (
        "testing_table",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'CBM_Testing')
        BEGIN
            CREATE TABLE dbo.CBM_Testing (
                Testing_ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                CBM_Technician_ID INT NULL,
                Equipment_ID INT NULL,
                Test_Date NVARCHAR(50) NULL,
                Result NVARCHAR(MAX) NULL,
                planner_id INT NULL,
                Test_Type NVARCHAR(255) NULL,
                Done BIT NOT NULL CONSTRAINT DF_CBM_Testing_Done DEFAULT (0),
                Status NVARCHAR(100) NULL,
                Alarm_Level NVARCHAR(100) NULL,
                Notes NVARCHAR(MAX) NULL,
                Done_Tested_Date NVARCHAR(50) NULL
            );
        END
        """
    ),
    # CBM_Testing_Attachments
    (
        "attach_table",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'CBM_Testing_Attachments')
        BEGIN
            CREATE TABLE dbo.CBM_Testing_Attachments (
                id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                testing_id INT NOT NULL,
                filename NVARCHAR(255) NOT NULL,
                path NVARCHAR(1024) NULL,
                uploaded_at NVARCHAR(50) NULL
            );
        END
        """
    ),
    # Alarm_Level (optional, used by models)
    (
        "alarm_table",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'Alarm_Level')
        BEGIN
            CREATE TABLE dbo.Alarm_Level (
                Alarm_ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                Equipment_ID INT NULL,
                Level NVARCHAR(100) NOT NULL,
                Message NVARCHAR(255) NULL
            );
        END
        """
    ),
    # Index and FK: CBM_Testing(planner_id) -> Planner(id)
    (
        "idx_planner_id",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CBM_Testing_planner_id' AND object_id = OBJECT_ID('dbo.CBM_Testing'))
        BEGIN
            CREATE INDEX IX_CBM_Testing_planner_id ON dbo.CBM_Testing(planner_id);
        END
        """
    ),
    (
        "fk_testing_planner",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CBM_Testing_Planner')
        BEGIN
            ALTER TABLE dbo.CBM_Testing WITH CHECK
            ADD CONSTRAINT FK_CBM_Testing_Planner
                FOREIGN KEY (planner_id) REFERENCES dbo.Planner(id) ON UPDATE NO ACTION;
            ALTER TABLE dbo.CBM_Testing CHECK CONSTRAINT FK_CBM_Testing_Planner;
        END
        """
    ),
    # FKs to Equipment and Technician
    (
        "fk_testing_equipment",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CBM_Testing_Equipment')
        BEGIN
            ALTER TABLE dbo.CBM_Testing WITH CHECK
            ADD CONSTRAINT FK_CBM_Testing_Equipment
                FOREIGN KEY (Equipment_ID) REFERENCES dbo.Equipment(EquipmentID);
            ALTER TABLE dbo.CBM_Testing CHECK CONSTRAINT FK_CBM_Testing_Equipment;
        END
        """
    ),
    (
        "fk_testing_technician",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CBM_Testing_Technician')
        BEGIN
            ALTER TABLE dbo.CBM_Testing WITH CHECK
            ADD CONSTRAINT FK_CBM_Testing_Technician
                FOREIGN KEY (CBM_Technician_ID) REFERENCES dbo.CBM_Technician(CBM_ID);
            ALTER TABLE dbo.CBM_Testing CHECK CONSTRAINT FK_CBM_Testing_Technician;
        END
        """
    ),
    # FK + index: Attachments(testing_id) -> CBM_Testing(Testing_ID)
    (
        "idx_attach_testing",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CBM_Testing_Attachments_testing_id' AND object_id = OBJECT_ID('dbo.CBM_Testing_Attachments'))
        BEGIN
            CREATE INDEX IX_CBM_Testing_Attachments_testing_id ON dbo.CBM_Testing_Attachments(testing_id);
        END
        """
    ),
    (
        "fk_attach_testing",
        """
        IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_CBM_Testing_Attachments_Testing')
        BEGIN
            ALTER TABLE dbo.CBM_Testing_Attachments WITH CHECK
            ADD CONSTRAINT FK_CBM_Testing_Attachments_Testing
                FOREIGN KEY (testing_id) REFERENCES dbo.CBM_Testing(Testing_ID) ON DELETE CASCADE;
            ALTER TABLE dbo.CBM_Testing_Attachments CHECK CONSTRAINT FK_CBM_Testing_Attachments_Testing;
        END
        """
    )
]


def main():
    conn = os.environ.get('MSSQL_CONN')
    if not conn:
        raise RuntimeError('MSSQL_CONN not set. Point it to CBM2.')
    eng = create_engine(conn, pool_pre_ping=True, future=True)
    with eng.begin() as c:
        for name, ddl in DDL_STATEMENTS:
            c.execute(text(ddl))
            print(f"Applied: {name}")
    print('Schema creation complete.')


if __name__ == '__main__':
    main()
