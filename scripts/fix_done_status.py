"""
Fix Done/Status helper.

Behavior (assumptions):
- Finds the single "longest not corrected" testing row: the oldest CBM_Testing row with
    COALESCE(Done,0)=0 and Status not 'waived', ordered by Test_Date ascending (oldest first).
- Deletes that row (removes the card).
- Finds up to 10 CBM_Testing rows where Alarm_Level is 'Critical' or 'Warning' and Done=1
    and Done_Tested_Date is present. Orders by Done_Tested_Date ascending (oldest done first).
- For each of those top-10, inserts a new CBM_Testing row copying relevant fields but
    setting Test_Date to today, Done=0, Status='ongoing', and Done_Tested_Date=NULL. The
    new rows are assigned to the planner_id of the deleted row when available; otherwise
    they are assigned to the most recent Planner row.

This lets the UI/dashboard replace an old open card with high-priority (Critical/Warning)
items that were done longest ago so they reappear as actionable items.

Run:
        python scripts\fix_done_status.py

Note: The script requires running inside the project's Python environment so that `app`
module is importable (same requirement as other scripts in ./scripts).
"""

from __future__ import annotations

import sys
from datetime import datetime, date
from sqlalchemy import text
from app import create_app
from app.models import db
def main():
    app = create_app()
    with app.app_context():
        with db.engine.begin() as conn:
            # 1) Find the oldest open (not Done) testing row, exclude waived
            oldest = conn.execute(text(
                """
                SELECT TOP 1 Testing_ID, planner_id
                FROM CBM_Testing
                WHERE COALESCE(Done,0) = 0
                  AND LOWER(TRIM(COALESCE(Status,''))) <> 'waived'
                ORDER BY
                  CASE WHEN Test_Date IS NULL OR TRIM(Test_Date) = '' THEN 1 ELSE 0 END,
                  Test_Date ASC
                """
            )).fetchone()

            if not oldest:
                print("No open (not-done) testing rows found to remove.")
                return

            oldest_id, oldest_planner = oldest

            # Delete the oldest open card
            conn.execute(text("DELETE FROM CBM_Testing WHERE Testing_ID = :id"), {"id": oldest_id})
            print(f"Deleted oldest open testing row: {oldest_id} (planner_id={oldest_planner})")

            # 2) Find top-10 Critical/Warning with oldest Done_Tested_Date
            rows = conn.execute(text(
                """
                SELECT TOP 10 Testing_ID, CBM_Technician_ID, Equipment_ID, Test_Type, Alarm_Level, Notes
                FROM CBM_Testing
                WHERE LOWER(TRIM(COALESCE(Alarm_Level,''))) IN ('critical','warning')
                  AND COALESCE(Done,0) = 1
                  AND TRIM(COALESCE(Done_Tested_Date,'')) <> ''
                ORDER BY CAST(Done_Tested_Date AS DATE) ASC
                """
            )).fetchall()

            if not rows:
                print("No completed Critical/Warning rows found to re-insert.")
                return

            # Determine a planner_id to use for inserts; use deleted one's planner if available,
            # else use the most recent planner id
            planner_id = oldest_planner
            if not planner_id:
                p = conn.execute(text("SELECT TOP 1 id FROM Planner ORDER BY id DESC")).fetchone()
                planner_id = p[0] if p else None

            inserted = 0
            today_iso = date.today().isoformat()
            for r in rows:
                _, tech_id, eq_id, test_type, alarm, notes = r
                conn.execute(text(
                    """
                    INSERT INTO CBM_Testing
                        (CBM_Technician_ID, Equipment_ID, Test_Date, Result, planner_id, Test_Type, Done, Status, Alarm_Level, Notes, Done_Tested_Date)
                    VALUES
                        (:tech, :eq, :tdate, NULL, :pid, :tt, 0, 'ongoing', :al, :nt, NULL)
                    """
                ), {
                    "tech": tech_id,
                    "eq": eq_id,
                    "tdate": today_iso,
                    "pid": planner_id,
                    "tt": test_type,
                    "al": alarm,
                    "nt": notes,
                })
                inserted += 1

            print(f"Inserted {inserted} replacement testing rows (from top-10 oldest done Critical/Warning).")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
