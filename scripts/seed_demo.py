from __future__ import annotations

"""
Seed demo data for charts and dashboard.

Highlights:
- Populates Equipment, CBM_Technician, Planner rows across recent weeks around today.
- Generates realistic dates (ISO week/day accurate) and status/alarm distributions.
- Ensures some 'Warning' items remain open from past weeks to drive the dashboard chart.
- Idempotent for equipment/technicians; planner/tasks seeding tries not to duplicate excessively.

Run:
    # Uses today's week/year +/- a range by default
    python -m scripts.seed_demo

Environment overrides:
- SEED_WEEK, SEED_YEAR      -> seed only a single target week/year
- SEED_PAST_WEEKS=int       -> how many past weeks to include (default 6)
- SEED_FUTURE_WEEKS=int     -> how many future weeks to include (default 0)
- SEED_PLANNERS_PER_WEEK    -> approx planner rows per week (default 10..14)
- SEED_RANDOM_SEED=int      -> fix RNG for reproducibility
- SEED_RESET_WINDOW=1|0     -> when 1, wipe Planner/CBM_Testing for the target window before seeding
- SEED_WARN_SHARE=float     -> fraction of Warning alarms (0..1, default 0.6)
- SEED_NORM_SHARE=float     -> fraction of Normal alarms (0..1, default 0.3)
- SEED_CRIT_SHARE=float     -> fraction of Critical alarms (0..1, default 0.1)
- SEED_WARN_DONE=float      -> probability a Warning item is done (default 0.10)
- SEED_NORM_DONE=float      -> probability a Normal item is done (default 0.80)
- SEED_CRIT_DONE=float      -> probability a Critical item is done (default 0.60)
 - SEED_CRIT_DONE=float      -> probability a Critical item is done (default 0.60)
 - SEED_WAIVED_MIN=int       -> min waived items per week (default 1)
 - SEED_WAIVED_MAX=int       -> max waived items per week (default 5)
"""

import os
import random
from datetime import datetime, timedelta, date
from sqlalchemy import text

from app import create_app
from app.models import db


EQUIPMENT_FIXTURES = {
    'Production': [
        'Extruder A', 'Extruder B', 'Mixer-01', 'Mixer-02', 'Conveyor-Left'
    ],
    'Utilities': [
        'Chiller-01', 'Chiller-02', 'Air Compressor-01', 'Cooling Tower'
    ],
    'QA Lab': [
        'Spectrometer', 'Microscope A', 'Microscope B'
    ],
    'Packaging': [
        'Sealer-01', 'Labeler-01', 'Palletizer'
    ],
}

TEST_TYPES = [
    'Vibration Analysis',
    'Oil Analysis',
    'Thermal Imaging',
    'Ultrasonic Analysis',
    'Motor Dynamic Analysis',
    'Ultrasonic Leak Detection',
    'Dynamic Balancing',
]

STATUSES = ['completed', 'done', 'ongoing', 'ongoing analysis', 'for revisit']
ALARMS = ['Normal', 'Warning', 'Critical']
SCHEDULE_TYPES = ['Planned', 'Unplanned', 'Validation']


def ensure_schema(conn):
    # MSSQL runtime: schema creation is handled by migration; no PRAGMA/SQLite DDL here
    return


def purge_other_test_types(conn):
    """Remove any existing CBM_Testing rows with Test_Type labeled 'Other'."""
    try:
        count = conn.execute(text(
            "SELECT COUNT(*) FROM CBM_Testing WHERE LOWER(TRIM(COALESCE(Test_Type,''))) = 'other'"
        )).scalar() or 0
        if count:
            conn.execute(text(
                "DELETE FROM CBM_Testing WHERE LOWER(TRIM(COALESCE(Test_Type,''))) = 'other'"
            ))
            print(f"Removed {count} 'Other' testing type rows.")
    except Exception as e:
        # Non-fatal; continue seeding
        print(f"Warning: failed to purge 'Other' testing type rows: {e}")


def upsert_equipment(conn):
    # Insert equipment fixtures if they don't exist
    for dept, machines in EQUIPMENT_FIXTURES.items():
        for m in machines:
            exists = conn.execute(
                text("SELECT TOP 1 1 FROM Equipment WHERE Department = :d AND Machine = :m"),
                {"d": dept, "m": m}
            ).fetchone()
            if not exists:
                conn.execute(
                    text("INSERT INTO Equipment (Department, Machine, Status) VALUES (:d, :m, 'Active')"),
                    {"d": dept, "m": m}
                )


def upsert_technicians(conn):
    techs = [
        ('Alice Santos', 'Vibration', 'alice.santos@example.com'),
        ('Ben Cruz', 'Oil Analysis', 'ben.cruz@example.com'),
        ('Carla Reyes', 'Thermal', 'carla.reyes@example.com'),
        ('Diego Lim', 'Ultrasonic', 'diego.lim@example.com'),
    ]
    for name, exp, email in techs:
        exists = conn.execute(
            text("SELECT TOP 1 1 FROM CBM_Technician WHERE Name = :n"),
            {"n": name}
        ).fetchone()
        if not exists:
            conn.execute(
                text("INSERT INTO CBM_Technician (Name, Expertise, Email) VALUES (:n, :e, :m)"),
                {"n": name, "e": exp, "m": email}
            )


def iso_monday(year: int, week_number: int) -> date:
    """Return the Monday date (ISO week start) for given ISO week/year."""
    return date.fromisocalendar(year, week_number, 1)


def seed_week(conn, week_number: int, year: int, target_rows: int = 12, age_weeks: int = 0):
    # Count existing planners
    cur_count = conn.execute(text(
        "SELECT COUNT(*) FROM Planner WHERE week_number = :w AND year = :y"
    ), {"w": week_number, "y": year}).scalar() or 0

    to_create = max(0, target_rows - cur_count)
    if to_create <= 0:
        print(f"Planner already has {cur_count} rows for week {week_number}, {year}. Adding tasks to existing rows only.")
    else:
        print(f"Creating {to_create} planner rows for week {week_number}, {year}.")

    # Pick some equipments (may be limited by env to a single equipment)
    all_equipment = conn.execute(text("SELECT Department, Machine FROM Equipment")).fetchall()
    if not all_equipment:
        print("No equipment found; aborting.")
        return

    # Environment controls to limit seeding to a single equipment
    # - SEED_EQUIPMENT='Machine Name' will restrict to that machine if found
    # - SEED_USE_SINGLE_EQUIPMENT=1 will force using only the first equipment found
    seed_equip_name = os.getenv('SEED_EQUIPMENT') or os.getenv('SEED_SINGLE_EQUIPMENT')
    if seed_equip_name:
        filtered = [r for r in all_equipment if (r[1] or '').strip().lower() == seed_equip_name.strip().lower()]
        if filtered:
            all_equipment = filtered
            print(f"Seeding restricted to equipment: {all_equipment[0][1]}")
        else:
            print(f"Warning: SEED_EQUIPMENT='{seed_equip_name}' not found; continuing with full equipment list.")
    elif (os.getenv('SEED_USE_SINGLE_EQUIPMENT') or '').strip().lower() in ('1', 'true', 'yes', 'on'):
        # Use the first equipment deterministically to keep demo compact
        first = all_equipment[0]
        all_equipment = [first]
        print(f"Seeding restricted to single equipment: {first[1]}")

    # Monday of the ISO week
    monday = datetime.combine(iso_monday(year, week_number), datetime.min.time())

    # Create planner rows
    created_ids: list[int] = []
    for i in range(to_create):
        dept, eqp = random.choice(all_equipment)
        pm_date_dt = (monday + timedelta(days=random.randint(0, 6)))
        pm_dt = pm_date_dt.date().isoformat()
        sched = random.choices(SCHEDULE_TYPES, weights=[6, 2, 1])[0]
        conn.execute(text(
            """
            INSERT INTO Planner (week_number, year, department, equipment, date, day, pm_date, schedule_type, proposed_target_date)
            VALUES (:w, :y, :d, :e, :date, :day, :pm, :sched, :ptd)
            """
        ), {
            "w": week_number,
            "y": year,
            "d": dept,
            "e": eqp,
            "date": pm_dt,
            "day": pm_date_dt.strftime('%A'),
            "pm": pm_dt,
            "sched": sched,
            "ptd": pm_dt,
    })
    pid = conn.execute(text("SELECT CAST(SCOPE_IDENTITY() AS INT)")).scalar()
    created_ids.append(pid)

    # Use both newly created and some existing planners for richer distribution
    existing_ids = [r[0] for r in conn.execute(text(
        "SELECT TOP 20 id FROM Planner WHERE week_number = :w AND year = :y ORDER BY id DESC"
    ), {"w": week_number, "y": year}).fetchall()]
    planner_ids = list(dict.fromkeys(created_ids + existing_ids))  # preserve order, unique

    # Seed tasks per planner
    for pid in planner_ids:
        # Map planner to equipment id
        prow = conn.execute(text("SELECT equipment, date FROM Planner WHERE id = :pid"), {"pid": pid}).fetchone()
        if not prow:
            continue
        eq_name, date_str = prow
        eq_row = conn.execute(text("SELECT TOP 1 EquipmentID FROM Equipment WHERE Machine = :m"), {"m": eq_name}).fetchone()
        equipment_id = eq_row[0] if eq_row else None

        # Ensure between 3-6 tasks per planner
        cur_tasks = conn.execute(text("SELECT COUNT(*) FROM CBM_Testing WHERE planner_id = :pid"), {"pid": pid}).scalar() or 0
        n_to_add = max(0, random.randint(3, 6) - cur_tasks)
        if n_to_add <= 0:
            continue
        types = random.sample(TEST_TYPES, k=min(n_to_add, len(TEST_TYPES)))
        # Load ratio config (safe to fetch each iteration in case caller changes env per run)
        def get_ratio(name: str, default: float) -> float:
            try:
                v = float(os.getenv(name) or default)
                if v < 0: v = 0.0
                return v
            except Exception:
                return default
        norm_share = get_ratio('SEED_NORM_SHARE', 0.30)
        warn_share = get_ratio('SEED_WARN_SHARE', 0.60)
        crit_share = get_ratio('SEED_CRIT_SHARE', 0.10)
        total_share = max(1e-6, norm_share + warn_share + crit_share)
        w_norm = norm_share / total_share
        w_warn = warn_share / total_share
        w_crit = crit_share / total_share
        p_warn_done = get_ratio('SEED_WARN_DONE', 0.10)
        p_norm_done = get_ratio('SEED_NORM_DONE', 0.80)
        p_crit_done = get_ratio('SEED_CRIT_DONE', 0.60)

        for tt in types:
            # Alarm distribution per configured weights
            alarm_choice = random.choices(population=ALARMS, weights=[w_norm, w_warn, w_crit])[0]

            # Completion likelihood depends on alarm level to achieve:
            # Warning (not done) >> Not Corrected (non-warning not done) and Corrected
            if alarm_choice == 'Warning':
                done_flag = 1 if random.random() < p_warn_done else 0
            elif alarm_choice == 'Critical':
                done_flag = 1 if random.random() < p_crit_done else 0
            else:  # Normal
                done_flag = 1 if random.random() < p_norm_done else 0

            # Derive status from done vs not-done
            if done_flag:
                status_choice = 'completed'
            else:
                status_choice = random.choices(
                    population=['ongoing', 'ongoing analysis', 'for revisit'],
                    weights=[60, 25, 15]
                )[0]

            # Done_Tested_Date for done ~ 80% of the time
            done_date = None
            if done_flag and random.random() < 0.8:
                done_date = (datetime.fromisoformat(date_str) + timedelta(days=random.randint(0, 2))).date().isoformat()

            # Enforce: if status will be 'completed' it must have a Done_Tested_Date.
            # Use the Test_Date as a sensible default if the random roll above did not set a date.
            if status_choice and status_choice.strip().lower() in ('completed', 'done') and not done_date:
                try:
                    # Prefer the test date from the planner row; fall back to today
                    done_date = date_str or datetime.now().date().isoformat()
                except Exception:
                    done_date = datetime.now().date().isoformat()

            # Occasional notes
            notes = None
            if random.random() < 0.4:
                notes = random.choice([
                    'OK', 'Recheck in 2 weeks', 'Vibes elevated on DE bearing', 'Oil sample pending', 'Thermal hotspot near coupling'
                ])

            conn.execute(text(
                """
                INSERT INTO CBM_Testing (CBM_Technician_ID, Equipment_ID, Test_Date, Result, planner_id, Test_Type, Done, Status, Alarm_Level, Notes, Done_Tested_Date)
                VALUES (NULL, :eqid, :tdate, NULL, :pid, :tt, :done, :st, :al, :nt, :dtd)
                """
            ), {
                "eqid": equipment_id,
                "tdate": date_str,
                "pid": pid,
                "tt": tt,
                "done": done_flag,
                "st": status_choice,
                "al": alarm_choice,
                "nt": notes,
                "dtd": done_date,
            })

    # Assign a small number of 'waived' items for this week (default 1-5)
    try:
        wmin = int(os.getenv('SEED_WAIVED_MIN') or 1)
    except Exception:
        wmin = 1
    try:
        wmax = int(os.getenv('SEED_WAIVED_MAX') or 5)
    except Exception:
        wmax = 5
    wmin = max(0, wmin)
    wmax = max(wmin, wmax)
    target_waived = random.randint(wmin, wmax) if wmax > 0 else 0
    if target_waived > 0:
        # Candidates: open, not already waived or completed/done
        cand_rows = conn.execute(text(
            """
            SELECT t.Testing_ID
            FROM CBM_Testing t
            JOIN Planner p ON p.id = t.planner_id
            WHERE p.week_number = :w AND p.year = :y
              AND COALESCE(t.Done,0) = 0
              AND LOWER(TRIM(COALESCE(t.Status,''))) NOT IN ('waived','completed','done')
            """
        ), {"w": week_number, "y": year}).fetchall()
        cand_ids = [r[0] for r in cand_rows]
        if cand_ids:
            k = min(target_waived, len(cand_ids))
            pick = random.sample(cand_ids, k)
            bind = {f"id{i}": pick[i] for i in range(len(pick))}
            inlist = ", ".join(":" + k for k in bind.keys())
            conn.execute(text(f"UPDATE CBM_Testing SET Status = 'waived' WHERE Testing_ID IN ({inlist})"), bind)

    # Age-based post processing: complete most tasks from previous weeks
    def get_ratio_env(name: str, default: float) -> float:
        try:
            v = float(os.getenv(name) or default)
            return max(0.0, min(1.0, v))
        except Exception:
            return default

    if age_weeks > 0:
        # Target open ratios by age
        target_ratio = (
            get_ratio_env('SEED_TARGET_OPEN_AGE1', 0.15) if age_weeks == 1 else
            get_ratio_env('SEED_TARGET_OPEN_AGE2', 0.08) if age_weeks == 2 else
            get_ratio_env('SEED_TARGET_OPEN_AGE3P', 0.03)
        )
        prefer_warn_open = (os.getenv('SEED_KEEP_WARNINGS_FIRST') or '1').strip().lower() in ('1','true','yes','on')

        # Gather open candidates for this week (excluding waived)
        rows = conn.execute(text(
            """
            SELECT t.Testing_ID, t.Alarm_Level, TRIM(COALESCE(t.Status,'')) AS Status, t.Done_Tested_Date, t.Test_Date
            FROM CBM_Testing t
            JOIN Planner p ON p.id = t.planner_id
            WHERE p.week_number = :w AND p.year = :y
              AND COALESCE(t.Done,0) = 0
              AND LOWER(TRIM(COALESCE(t.Status,''))) <> 'waived'
            """
        ), {"w": week_number, "y": year}).mappings().fetchall()

        if rows:
            ids = [r['Testing_ID'] for r in rows]
            n = len(ids)
            keep = int(round(n * target_ratio))
            keep = max(0, min(n, keep))

            # Prefer to keep warnings open
            if prefer_warn_open:
                warn_ids = [r['Testing_ID'] for r in rows if (r.get('Alarm_Level') or '').strip().lower() == 'warning']
                non_ids = [r['Testing_ID'] for r in rows if (r.get('Alarm_Level') or '').strip().lower() != 'warning']
                random.shuffle(warn_ids)
                random.shuffle(non_ids)
                keep_list = warn_ids[:keep] if keep <= len(warn_ids) else warn_ids + non_ids[:(keep - len(warn_ids))]
            else:
                keep_list = random.sample(ids, keep) if keep > 0 else []

            keep_set = set(keep_list)
            close_list = [tid for tid in ids if tid not in keep_set]

            # Close items: mark as completed with done dates near test date
            for tid in close_list:
                try:
                    trow = conn.execute(text("SELECT Test_Date FROM CBM_Testing WHERE Testing_ID = :id"), {"id": tid}).fetchone()
                    if trow and trow[0]:
                        try:
                            base_dt = datetime.fromisoformat(trow[0])
                        except Exception:
                            base_dt = datetime.now()
                    else:
                        base_dt = datetime.now()
                    done_dt = (base_dt + timedelta(days=random.randint(0, 3))).date().isoformat()
                    conn.execute(text(
                        "UPDATE CBM_Testing SET Done = 1, Status = 'completed', Done_Tested_Date = :d WHERE Testing_ID = :id"
                    ), {"d": done_dt, "id": tid})
                except Exception:
                    pass

            # For remaining open items in older weeks, bias status to 'for revisit'
            if age_weeks >= 2 and keep_list:
                try:
                    # Flip ~60% to 'for revisit'
                    k = max(1, int(round(len(keep_list) * 0.6)))
                    sample_ids = random.sample(keep_list, k)
                    bind = {f"kid{i}": sample_ids[i] for i in range(len(sample_ids))}
                    inlist = ", ".join(":" + k for k in bind.keys())
                    conn.execute(text(f"UPDATE CBM_Testing SET Status = 'for revisit' WHERE Testing_ID IN ({inlist})"), bind)
                except Exception:
                    pass

    print(f"Seed complete. Planners used: {len(planner_ids)}. New planners: {len(created_ids)}.")

    # Final safety sweep: ensure any row with Status 'completed' or 'done' has a Done_Tested_Date.
    try:
        conn.execute(text(
            """
            UPDATE CBM_Testing
            SET Done_Tested_Date = COALESCE(
                NULLIF(TRIM(COALESCE(Test_Date, '')), ''),
                CONVERT(VARCHAR(10), GETDATE(), 23)
            )
            WHERE (LOWER(TRIM(COALESCE(Status, ''))) = 'completed' OR LOWER(TRIM(COALESCE(Status, ''))) = 'done')
              AND (Done_Tested_Date IS NULL OR TRIM(COALESCE(Done_Tested_Date, '')) = '')
            """
        ))
    except Exception:
        # Non-fatal; seeding should continue even if DB doesn't accept the sweep for some reason
        pass


def seed_many_weeks(conn, center_date: date, past_weeks: int = 6, future_weeks: int = 0, planners_per_week: tuple[int,int] = (10,14)):
    """Seed a window of weeks around center_date.
    - Creates a spread so dashboards have historical context (old warnings stay open).
    - planners_per_week is a (min,max) range used to vary target_rows per week.
    """
    # Ensure base data
    upsert_equipment(conn)
    upsert_technicians(conn)

    center_iso = center_date.isocalendar()
    center_week = center_iso[1]
    center_year = center_iso[0]

    # Seed past weeks (older first) then current then future
    for offset in range(past_weeks, 0, -1):
        dt = center_date - timedelta(weeks=offset)
        iso = dt.isocalendar()
        monday = iso_monday(iso[0], iso[1])
        age_weeks = max(0, (center_date - monday).days // 7)
        seed_week(conn, iso[1], iso[0], target_rows=random.randint(*planners_per_week), age_weeks=age_weeks)
    seed_week(conn, center_week, center_year, target_rows=random.randint(*planners_per_week), age_weeks=0)
    for offset in range(1, future_weeks + 1):
        dt = center_date + timedelta(weeks=offset)
        iso = dt.isocalendar()
        seed_week(conn, iso[1], iso[0], target_rows=random.randint(*planners_per_week), age_weeks=-offset)


def delete_window(conn, center_date: date, past_weeks: int, future_weeks: int):
    """Delete Planner and related CBM_Testing rows in a window of weeks around center_date.
    Deletes CBM_Testing first, then Planner, for referential integrity.
    """
    # Build pairs
    pairs = []
    for offset in range(past_weeks, 0, -1):
        d = center_date - timedelta(weeks=offset)
        iso = d.isocalendar()
        pairs.append((iso[0], iso[1]))
    iso = center_date.isocalendar()
    pairs.append((iso[0], iso[1]))
    for offset in range(1, future_weeks + 1):
        d = center_date + timedelta(weeks=offset)
        iso = d.isocalendar()
        pairs.append((iso[0], iso[1]))
    # Delete in chunks
    for y, w in pairs:
        # Get planner ids
        pids = [r[0] for r in conn.execute(text("SELECT id FROM Planner WHERE year = :y AND week_number = :w"), {"y": y, "w": w}).fetchall()]
        if not pids:
            continue
        # Delete CBM_Testing rows for these planners
        bind = {f"pid{i}": pid for i, pid in enumerate(pids)}
        inlist = ", ".join(":" + k for k in bind.keys())
        conn.execute(text(f"DELETE FROM CBM_Testing WHERE planner_id IN ({inlist})"), bind)
        # Delete Planner rows
        conn.execute(text(f"DELETE FROM Planner WHERE id IN ({inlist})"), bind)


def main():
    app = create_app()
    with app.app_context():
        with db.engine.begin() as conn:
            ensure_schema(conn)
            # Proactively remove any previously seeded 'Other' test type data
            purge_other_test_types(conn)
            # RNG seed (optional)
            seed_val = os.getenv('SEED_RANDOM_SEED')
            if seed_val and seed_val.isdigit():
                random.seed(int(seed_val))

            # Determine target mode
            env_week = os.getenv('SEED_WEEK')
            env_year = os.getenv('SEED_YEAR')
            now = datetime.now()
            if env_week and env_year:
                week = int(env_week)
                year = int(env_year)
                # Compute age relative to today
                center = now.date()
                monday = iso_monday(year, week)
                age_weeks = max(0, (center - monday).days // 7)
                seed_week(conn, week, year, target_rows=random.randint(10,14), age_weeks=age_weeks)
            else:
                past_weeks = int(os.getenv('SEED_PAST_WEEKS') or 6)
                future_weeks = int(os.getenv('SEED_FUTURE_WEEKS') or 0)
                reset = (os.getenv('SEED_RESET_WINDOW') or '0').strip() in ('1','true','yes','on')
                center = now.date()
                if reset:
                    delete_window(conn, center, past_weeks, future_weeks)
                # Use today's date as center
                seed_many_weeks(conn, center, past_weeks=past_weeks, future_weeks=future_weeks, planners_per_week=(10,14))


if __name__ == '__main__':
    main()
