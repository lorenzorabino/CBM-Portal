# create a small inspector script
$script = @'
import sqlite3
db = r"database/portal_demo3.db"
cols = {"Testing_ID","planner_id","Test_Type","Alarm_Level","Done_Tested_Date","proposed_target_date","schedule_type","week_number","year","department","equipment","Status"}
con = sqlite3.connect(db)
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in tables:
    try:
        info = cur.execute(f"PRAGMA table_info('{t}')").fetchall()
    except Exception as e:
        continue
    names = [c[1] for c in info]
    hits = cols & set(names)
    if hits:
        print(t, sorted(hits))
con.close()
'@

# save and run using the project's venv python if available, otherwise default python
$scriptPath = ".\inspect_validation_tables.py"
Set-Content -Path $scriptPath -Value $script -Encoding UTF8

# prefer venv python if present
$venvPy = Join-Path -Path (Get-Location) -ChildPath "cbm_venv\Scripts\python.exe"
if (Test-Path $venvPy) { & $venvPy $scriptPath } else { python $scriptPath }