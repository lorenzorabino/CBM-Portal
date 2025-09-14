# Set MSSQL_CONN here for local development.
# Copy this file to mssql_conn.ps1 and edit with your server details.
# Example with SQL auth:
# $env:MSSQL_CONN = "mssql+pyodbc://USERNAME:PASSWORD@SERVER,1433/Database?driver=ODBC+Driver+17+for+SQL+Server;TrustServerCertificate=yes"
# Example with Windows auth:
# $env:MSSQL_CONN = "mssql+pyodbc://@SERVER/Database?driver=ODBC+Driver+18+for+SQL+Server;Trusted_Connection=yes;TrustServerCertificate=yes"

# Default to CBM2 database (deprecated: CBM). Update server/creds as needed.
$env:MSSQL_CONN = "mssql+pyodbc://sa:pmdatascience@172.31.3.40,1433/CBM2?driver=ODBC+Driver+17+for+SQL+Server"
