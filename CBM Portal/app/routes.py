from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import text
from .models import db, AlarmLevel, CBMTechnician, CBMTesting, Equipment

main = Blueprint('main', __name__)

@main.route('/')
def index():
    # Avoid loading entire tables on the dashboard (can be heavy). Use empty lists; pages load their own data.
    alarms = []
    technicians = []
    testings = []
    equipments = []
    # Dashboard filters (week/year)
    from datetime import datetime
    now = datetime.now()
    try:
        cur_week = now.isocalendar()[1]
    except Exception:
        cur_week = int(now.strftime('%W')) or 1
    week = (request.args.get('week') or '').strip()
    year = (request.args.get('year') or '').strip()
    try:
        sel_week = int(week) if week else cur_week
    except Exception:
        sel_week = cur_week
    try:
        sel_year = int(year) if year else now.year
    except Exception:
        sel_year = now.year
    # KPIs and queues
    from sqlalchemy import text
    counts = {
        'total': 0,
        'completed': 0,
        'ongoing': 0,
        'ongoing_analysis': 0,
    'sending_report': 0,
    'active_in_progress': 0,
    'waived': 0,
        'for_revisit': 0,
        'needs_done_date': 0,
    'alarm_critical': 0,
    'alarm_warning': 0,
    'alarm_crit_warn': 0,
        'worst_alarm': '',
    'planned_tests': 0,
    'unplanned_tests': 0,
    'validation_tests': 0,
    'other_schedule_tests': 0,
    }
    board_rows = []
    # Removed warning_longest KPI card context
    missing_done = []  # [{testing_id, test_type, planner_id}]
    alarm_hot = []     # [{testing_id, test_type, planner_id, alarm_level, category}]
    recent_planners = []  # [{id, department, equipment, week_number, year}]
    recent_attachments = []  # [{id, testing_id, filename}]
    try:
        with db.engine.begin() as conn:
            # Counts
            base = "FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id WHERE p.week_number = :w AND p.year = :y"
            def scalar(sql, params):
                return conn.execute(text(sql), params).scalar() or 0
            counts['total'] = scalar("SELECT COUNT(*) " + base, {"w": sel_week, "y": sel_year})
            counts['completed'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed'))",
                {"w": sel_week, "y": sel_year}
            )
            counts['ongoing'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND COALESCE(t.Done,0)=0 AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('ongoing','todo','')",
                {"w": sel_week, "y": sel_year}
            )
            counts['ongoing_analysis'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Status,''))) = 'ongoing analysis'",
                {"w": sel_week, "y": sel_year}
            )
            counts['sending_report'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('sending','sending report','report sending','sending-report')",
                {"w": sel_week, "y": sel_year}
            )
            counts['active_in_progress'] = (
                int(counts.get('ongoing') or 0)
                + int(counts.get('ongoing_analysis') or 0)
                + int(counts.get('sending_report') or 0)
            )
            counts['for_revisit'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Status,''))) = 'for revisit'",
                {"w": sel_week, "y": sel_year}
            )
            counts['waived'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Status,''))) = 'waived'",
                {"w": sel_week, "y": sel_year}
            )
            counts['needs_done_date'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND TRIM(COALESCE(t.Done_Tested_Date,'')) = ''",
                {"w": sel_week, "y": sel_year}
            )
            # Schedule-type breakdown aligned to Total (count tests by planner schedule type)
            counts['planned_tests'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'planned'",
                {"w": sel_week, "y": sel_year}
            )
            counts['unplanned_tests'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'unplanned'",
                {"w": sel_week, "y": sel_year}
            )
            counts['validation_tests'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'validation'",
                {"w": sel_week, "y": sel_year}
            )
            counts['other_schedule_tests'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(p.schedule_type,''))) NOT IN ('planned','unplanned','validation')",
                {"w": sel_week, "y": sel_year}
            )
            counts['alarm_critical'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'critical'",
                {"w": sel_week, "y": sel_year}
            )
            counts['alarm_warning'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'warning'",
                {"w": sel_week, "y": sel_year}
            )
            counts['alarm_crit_warn'] = int(counts['alarm_critical']) + int(counts['alarm_warning'])
            # Worst alarm
            counts['worst_alarm'] = conn.execute(text(
                """
                SELECT CASE MAX(CASE LOWER(TRIM(tt.Alarm_Level))
                                WHEN 'critical' THEN 3 WHEN 'warning' THEN 2 WHEN 'normal' THEN 1 ELSE 0 END)
                       WHEN 3 THEN 'Critical' WHEN 2 THEN 'Warning' WHEN 1 THEN 'Normal' ELSE '' END
                FROM CBM_Testing tt JOIN Planner p ON p.id = tt.planner_id
                WHERE p.week_number = :w AND p.year = :y
                """
            ), {"w": sel_week, "y": sel_year}).scalar() or ''
            # Missing Done Tested Date list
            rows = conn.execute(text(
                """
                SELECT t.Testing_ID, t.Test_Type, t.planner_id
                FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id
                WHERE p.week_number = :w AND p.year = :y
                  AND TRIM(COALESCE(t.Done_Tested_Date,'')) = ''
                ORDER BY t.Testing_ID DESC LIMIT 10
                """
            ), {"w": sel_week, "y": sel_year}).fetchall()
            for rid, rtype, rpid in rows:
                missing_done.append({"testing_id": rid, "test_type": rtype, "planner_id": rpid})
            # Critical/Warning alarms list
            rows = conn.execute(text(
                """
                SELECT t.Testing_ID, t.Test_Type, t.planner_id, t.Alarm_Level
                FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id
                WHERE p.week_number = :w AND p.year = :y
                  AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) IN ('critical','warning')
                ORDER BY t.Testing_ID DESC LIMIT 10
                """
            ), {"w": sel_week, "y": sel_year}).fetchall()
            def to_cat(tt: str) -> str:
                key = (tt or '').lower().strip()
                if 'vibration' in key: return 'vibration'
                if 'oil' in key: return 'oil'
                if 'thermal' in key: return 'thermal'
                if 'ultrasonic leak' in key: return 'leak_detection'
                if 'ultrasonic' in key: return 'ultrasonic'
                if 'motor dynamic' in key: return 'motor_dynamic'
                if 'balancing' in key: return 'balancing'
                return 'other'
            for rid, rtype, rpid, alarm in rows:
                alarm_hot.append({
                    "testing_id": rid, "test_type": rtype, "planner_id": rpid,
                    "alarm_level": alarm, "category": to_cat(rtype)
                })
            # Removed warning_longest KPI card logic
            # Recent planners
            rp = conn.execute(text(
                "SELECT id, department, equipment, week_number, year, pm_date FROM Planner ORDER BY id DESC LIMIT 5"
            )).fetchall()
            for r in rp:
                # compute PM week number from pm_date when available
                pm_week = None
                try:
                    if r[5]:
                        from datetime import datetime
                        ds = str(r[5])[:10]
                        dt = datetime.fromisoformat(ds).date()
                        pm_week = dt.isocalendar()[1]
                except Exception:
                    pm_week = None
                recent_planners.append({
                    "id": r[0], "department": r[1], "equipment": r[2], "week_number": r[3], "year": r[4],
                    "pm_date": r[5], "pm_week_number": pm_week
                })
            # Recent attachments
            ra = conn.execute(text(
                "SELECT id, testing_id, filename FROM CBM_Testing_Attachments ORDER BY uploaded_at DESC LIMIT 5"
            )).fetchall()
            for r in ra:
                recent_attachments.append({"id": r[0], "testing_id": r[1], "filename": r[2]})
            # Board rows grouped by Planner with progress and alarm
            board_sql = text(
                """
                SELECT p.id, p.week_number, p.year, p.department, p.equipment, p.pm_date, p.schedule_type,
                  COALESCE((SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id), 0) AS total_tests,
                  COALESCE((SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id AND (COALESCE(tt.Done,0)=1 OR LOWER(TRIM(COALESCE(tt.Status,''))) IN ('completed','done'))),0) AS completed_count,
                  COALESCE((SELECT CASE MAX(CASE LOWER(TRIM(tt.Alarm_Level)) WHEN 'critical' THEN 3 WHEN 'warning' THEN 2 WHEN 'normal' THEN 1 ELSE 0 END)
                            WHEN 3 THEN 'Critical' WHEN 2 THEN 'Warning' WHEN 1 THEN 'Normal' ELSE '' END
                           FROM CBM_Testing tt WHERE tt.planner_id = p.id), '') AS worst_alarm,
                  COALESCE((SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id AND TRIM(COALESCE(tt.Done_Tested_Date,''))<>''),0) AS done_date_count
                FROM Planner p
                WHERE p.week_number = :w AND p.year = :y
                ORDER BY p.id DESC LIMIT 100
                """
            )
            rows = conn.execute(board_sql, {"w": sel_week, "y": sel_year}).fetchall()
            for r in rows:
                # compute pm week number from pm_date if present
                pm_week = None
                try:
                    if r[5]:
                        from datetime import datetime
                        ds = str(r[5])[:10]
                        dt = datetime.fromisoformat(ds).date()
                        pm_week = dt.isocalendar()[1]
                except Exception:
                    pm_week = None
                board_rows.append({
                    "id": r[0],
                    "week_number": r[1],
                    "year": r[2],
                    "department": r[3],
                    "equipment": r[4],
                    "pm_date": r[5],
                    "pm_week_number": pm_week,
                    "schedule_type": r[6],
                    "total_tests": r[7],
                    "completed_count": r[8],
                    "worst_alarm": r[9],
                    "done_date_count": r[10],
                })

            # Equipment-level aggregation for the week (used to render equipment cards with progress)
            equipment_board = []
            eq_sql = text(
                """
                SELECT e.EquipmentID as id, e.Department as department, COALESCE(e.Machine, e.Equipment, '') as equipment,
                  COALESCE((SELECT COUNT(*) FROM CBM_Testing tt JOIN Planner p2 ON p2.id = tt.planner_id WHERE tt.Equipment_ID = e.EquipmentID AND p2.week_number = :w AND p2.year = :y), 0) AS total_tests,
                  COALESCE((SELECT COUNT(*) FROM CBM_Testing tt JOIN Planner p2 ON p2.id = tt.planner_id WHERE tt.Equipment_ID = e.EquipmentID AND p2.week_number = :w AND p2.year = :y AND (COALESCE(tt.Done,0)=1 OR LOWER(TRIM(COALESCE(tt.Status,''))) IN ('completed','done'))), 0) AS completed_count
                FROM Equipment e
                WHERE EXISTS (
                  SELECT 1 FROM CBM_Testing tt JOIN Planner p2 ON p2.id = tt.planner_id
                  WHERE tt.Equipment_ID = e.EquipmentID AND p2.week_number = :w AND p2.year = :y
                )
                ORDER BY e.EquipmentID LIMIT 200
                """
            )
            try:
                erows = conn.execute(eq_sql, {"w": sel_week, "y": sel_year}).fetchall()
                for rr in erows:
                    equipment_board.append({
                        "id": rr[0],
                        "department": rr[1],
                        "equipment": rr[2] or '',
                        "total_tests": int(rr[3] or 0),
                        "completed_count": int(rr[4] or 0),
                    })
            except Exception:
                equipment_board = []
    except Exception:
        pass
    return render_template(
        'index.html',
        alarms=alarms,
        technicians=technicians,
        testings=testings,
        equipments=equipments,
        kpi_counts=counts,
        sel_week=sel_week,
        sel_year=sel_year,
        missing_done=missing_done,
        alarm_hot=alarm_hot,
        recent_planners=recent_planners,
        recent_attachments=recent_attachments,
        board_rows=board_rows,
    equipment_board=equipment_board,
        # Removed warning_longest KPI card context
    )


@main.route('/api/dashboard/weekly_metrics')
def api_weekly_metrics():
    """Return weekly metrics over the last N weeks.

    Query params:
    - weeks: number of weeks to include (default 12, max 52)
    """
    from datetime import date, timedelta
    try:
        n = int((request.args.get('weeks') or '12').strip())
        if n < 1: n = 12
        if n > 52: n = 52
    except Exception:
        n = 12
    basis = (request.args.get('basis') or 'planner').strip().lower()
    today = date.today()
    # Build list of (year, week) for last n weeks including current, in ascending order
    pairs = []
    for k in range(n - 1, -1, -1):
        d = today - timedelta(weeks=k)
        iso = d.isocalendar()
        pairs.append((iso[0], iso[1]))
    # Unique pairs and index map
    uniq = []
    seen = set()
    for y, w in pairs:
        key = (y, w)
        if key not in seen:
            seen.add(key)
            uniq.append(key)
    # Build OR clause for the selected weeks
    clauses = []
    params = {}
    for i, (y, w) in enumerate(uniq):
        clauses.append(f"(p.year = :y{i} AND p.week_number = :w{i})")
        params[f"y{i}"] = y
        params[f"w{i}"] = w
    if not clauses:
        return jsonify(dict(labels=[], completed=[], inprogress=[], inprogress_breakdown=dict(ongoing=[], analysis=[], sending=[]), alarms=dict(critical=[], warning=[], total=[])))
    sql = (
        "SELECT p.year AS y, p.week_number AS w, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed')) THEN 1 ELSE 0 END) AS completed, "
        "SUM(CASE WHEN (COALESCE(t.Done,0)=0 AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('ongoing','todo','')) THEN 1 ELSE 0 END) AS ongoing, "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Status,''))) = 'ongoing analysis' THEN 1 ELSE 0 END) AS analysis, "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Status,''))) IN ('sending','sending report','report sending','sending-report') THEN 1 ELSE 0 END) AS sending, "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Status,''))) = 'for revisit' THEN 1 ELSE 0 END) AS for_revisit, "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Status,''))) = 'waived' THEN 1 ELSE 0 END) AS waived, "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'critical' THEN 1 ELSE 0 END) AS alarm_critical, "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'warning' THEN 1 ELSE 0 END) AS alarm_warning, "
    "/* Corrected from Warning (completed warnings) */ "
    "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,'')))='warning' AND (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed')) THEN 1 ELSE 0 END) AS corrected_warning, "
        "/* Warning and not completed */ "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,'')))='warning' AND NOT (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed')) THEN 1 ELSE 0 END) AS warn_not_done, "
        "/* Not corrected (not completed) and not warning */ "
    "SUM(CASE WHEN NOT (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed')) AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) <> 'warning' THEN 1 ELSE 0 END) AS not_corrected, "
    "/* Planned tests count (by Planner schedule_type) */ "
    "SUM(CASE WHEN LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'planned' THEN 1 ELSE 0 END) AS planned_tests, "
        "/* Critical closed (completed critical) */ "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,'')))='critical' AND (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed')) THEN 1 ELSE 0 END) AS corrected_critical, "
        "/* Critical and not completed */ "
        "SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,'')))='critical' AND NOT (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed')) THEN 1 ELSE 0 END) AS critical_not_done "
        "FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id "
        f"WHERE {' OR '.join(clauses)} "
        "GROUP BY p.year, p.week_number"
    )
    data_map = {}
    try:
        with db.engine.begin() as conn:
            for r in conn.execute(text(sql), params):
                key = (int(r[0]), int(r[1]))
                data_map[key] = dict(
                    total=int(r[2] or 0),
                    completed=int(r[3] or 0),
                    ongoing=int(r[4] or 0),
                    analysis=int(r[5] or 0),
                    sending=int(r[6] or 0),
                    for_revisit=int(r[7] or 0),
                    waived=int(r[8] or 0),
                    alarm_critical=int(r[9] or 0),
                    alarm_warning=int(r[10] or 0),
                    corrected_warning=int(r[11] or 0),
                    warn_not_done=int(r[12] or 0),
                    not_corrected=int(r[13] or 0),
                    planned_tests=int(r[14] or 0),
                    corrected_critical=int(r[15] or 0),
                    critical_not_done=int(r[16] or 0),
                )
    except Exception:
        data_map = {}
    labels = [f"{y}-W{w:02d}" for (y, w) in pairs]
    pair_index = { (y,w): i for i,(y,w) in enumerate(pairs) }
    total = []
    completed = []
    ongoing = []
    analysis = []
    sending = []
    revisit = []
    waived = []
    acrit = []
    awarn = []
    corrected_warning = []
    warn_not_done = []
    not_corrected = []
    planned = []
    for y, w in pairs:
        d = data_map.get((y, w), {})
        total.append(int(d.get('total', 0)))
        completed.append(int(d.get('completed', 0)))
        ongoing.append(int(d.get('ongoing', 0)))
        analysis.append(int(d.get('analysis', 0)))
        sending.append(int(d.get('sending', 0)))
        revisit.append(int(d.get('for_revisit', 0)))
        waived.append(int(d.get('waived', 0)))
        acrit.append(int(d.get('alarm_critical', 0)))
        awarn.append(int(d.get('alarm_warning', 0)))
        corrected_warning.append(int(d.get('corrected_warning', 0)))
        warn_not_done.append(int(d.get('warn_not_done', 0)))
        not_corrected.append(int(d.get('not_corrected', 0)))
        planned.append(int(d.get('planned_tests', 0)))
    # Defaults (planner basis for closed counts)
    resp = dict(
        labels=labels,
        total=total,
        completed=completed,
        inprogress=[(ongoing[i] + analysis[i] + sending[i]) for i in range(len(labels))],
        inprogress_breakdown=dict(ongoing=ongoing, analysis=analysis, sending=sending),
        for_revisit=revisit,
        waived=waived,
        alarms=dict(critical=acrit, warning=awarn, total=[(acrit[i] + awarn[i]) for i in range(len(labels))]),
        corrected=corrected_warning,
        warning=warn_not_done,
        not_corrected=not_corrected,
        planned=planned,
        # New: open vs closed split per alarm type (grouped by planner week)
        warnings_open=warn_not_done,
        warnings_closed=corrected_warning,
        criticals_open=[int(data_map.get((y,w),{}).get('critical_not_done',0)) for (y,w) in pairs],
        criticals_closed=[int(data_map.get((y,w),{}).get('corrected_critical',0)) for (y,w) in pairs],
    )
    # Also compute closures grouped by actual Done_Tested_Date (done-week) so the UI can plot corrections by completion week
    corrected_by_done = [0] * len(labels)
    try:
        from datetime import datetime
        with db.engine.begin() as conn:
            rows = conn.execute(text(
                """
                SELECT TRIM(COALESCE(t.Done_Tested_Date,'')) AS dtd,
                       LOWER(TRIM(COALESCE(t.Alarm_Level,''))) AS alarm
                FROM CBM_Testing t
                WHERE (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed'))
                  AND TRIM(COALESCE(t.Done_Tested_Date,'')) <> ''
                """
            )).fetchall()
            for dtd, alarm in rows:
                try:
                    ds = str(dtd)[:10]
                    dt = datetime.fromisoformat(ds).date()
                    iso = dt.isocalendar()
                    key = (int(iso[0]), int(iso[1]))
                    idx = pair_index.get(key)
                    if idx is None:
                        continue
                    if alarm == 'warning' or alarm == 'critical':
                        corrected_by_done[idx] += 1
                except Exception:
                    continue
    except Exception:
        pass
    # expose as a separate field; UI will use this for the line series
    resp['corrected_by_done'] = corrected_by_done
    return jsonify(resp)


@main.route('/api/dashboard/alarm_split')
def api_alarm_split():
    """Return alarm split for a given week/year (Critical vs Warning)."""
    week = (request.args.get('week') or '').strip()
    year = (request.args.get('year') or '').strip()
    try:
        w = int(week)
        y = int(year)
    except Exception:
        # Fallback to current from index route logic
        from datetime import datetime
        now = datetime.now()
        try:
            w = now.isocalendar()[1]
        except Exception:
            w = int(now.strftime('%W')) or 1
        y = now.year
    counts = dict(critical=0, warning=0)
    try:
        with db.engine.begin() as conn:
            base = "FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id WHERE p.week_number = :w AND p.year = :y"
            def scalar(sql, params):
                return conn.execute(text(sql), params).scalar() or 0
            counts['critical'] = scalar("SELECT COUNT(*) " + base + " AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'critical'", {"w": w, "y": y})
            counts['warning'] = scalar("SELECT COUNT(*) " + base + " AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'warning'", {"w": w, "y": y})
    except Exception:
        pass
    return jsonify(counts)


@main.route('/api/dashboard/kpi_details')
def api_kpi_details():
    """Return the underlying items for a KPI box for the selected week/year.

    Query params:
    - type: one of [total, completed, in_progress, for_revisit, waived, alarms]
    - week, year: optional; defaults to current week/year
    """
    ktype = (request.args.get('type') or '').strip().lower()
    week = (request.args.get('week') or '').strip()
    year = (request.args.get('year') or '').strip()
    # Defaults aligned with index route
    from datetime import datetime
    now = datetime.now()
    try:
        cur_week = now.isocalendar()[1]
    except Exception:
        cur_week = int(now.strftime('%W')) or 1
    try:
        w = int(week) if week else cur_week
    except Exception:
        w = cur_week
    try:
        y = int(year) if year else now.year
    except Exception:
        y = now.year

    valid_types = {'total','completed','in_progress','for_revisit','waived','alarms'}
    if ktype not in valid_types:
        return jsonify(dict(title='Invalid type', items=[])), 400

    title_map = {
        'total': 'All Tests (This Week)',
        'completed': 'Completed Tests (This Week)',
        'in_progress': 'In-Progress Tests (This Week)',
        'for_revisit': 'For Revisit (This Week)',
        'waived': 'Waived (This Week)',
        'alarms': 'Alarms: Critical & Warning (This Week)',
    }
    # Base selection
    base = (
        "SELECT t.Testing_ID AS id, "
        "TRIM(COALESCE(t.Test_Type,'')) AS test_type, "
        "COALESCE(NULLIF(TRIM(t.Status), ''), CASE WHEN COALESCE(t.Done,0)=1 THEN 'done' END, '') AS status, "
        "TRIM(COALESCE(t.Alarm_Level,'')) AS alarm_level, "
        "TRIM(COALESCE(p.department,'')) AS department, "
        "TRIM(COALESCE(p.equipment,'')) AS equipment, "
        "TRIM(COALESCE(p.schedule_type,'')) AS schedule_type, "
        "TRIM(COALESCE(t.Done_Tested_Date,'')) AS done_date "
        "FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id "
        "WHERE p.week_number = :w AND p.year = :y"
    )
    where_extra = ""
    if ktype == 'completed':
        where_extra = " AND (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed'))"
    elif ktype == 'in_progress':
        where_extra = (
            " AND ( (COALESCE(t.Done,0)=0 AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('ongoing','todo','')) "
            " OR LOWER(TRIM(COALESCE(t.Status,''))) = 'ongoing analysis' "
            " OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('sending','sending report','report sending','sending-report') )"
        )
    elif ktype == 'for_revisit':
        where_extra = " AND LOWER(TRIM(COALESCE(t.Status,''))) = 'for revisit'"
    elif ktype == 'waived':
        where_extra = " AND LOWER(TRIM(COALESCE(t.Status,''))) = 'waived'"
    elif ktype == 'alarms':
        where_extra = " AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) IN ('critical','warning')"

    sql = base + where_extra + " ORDER BY p.department, p.equipment, t.Testing_ID DESC LIMIT 1000"
    items = []
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(text(sql), {"w": w, "y": y}).mappings().fetchall()
            for r in rows:
                items.append(dict(
                    id=r.get('id'),
                    test_type=r.get('test_type'),
                    status=r.get('status') or 'todo',
                    alarm_level=r.get('alarm_level') or '',
                    department=r.get('department'),
                    equipment=r.get('equipment'),
                    schedule_type=r.get('schedule_type'),
                    done_date=r.get('done_date') or '',
                ))
    except Exception:
        items = []
    return jsonify(dict(title=title_map.get(ktype, ktype), items=items, count=len(items), week=w, year=y))


@main.route('/api/dashboard/kpi_counts')
def api_kpi_counts():
    """Return KPI counts for the dashboard for either weekly or all-time scope.

    Query params:
    - scope: 'weekly' (default) or 'all' (alias: 'all-time')
    - week, year: used when scope=weekly (defaults to current)
    """
    scope = (request.args.get('scope') or 'weekly').strip().lower()
    week = (request.args.get('week') or '').strip()
    year = (request.args.get('year') or '').strip()
    # Defaults aligned with index route
    from datetime import datetime
    now = datetime.now()
    try:
        cur_week = now.isocalendar()[1]
    except Exception:
        cur_week = int(now.strftime('%W')) or 1
    try:
        w = int(week) if week else cur_week
    except Exception:
        w = cur_week
    try:
        y = int(year) if year else now.year
    except Exception:
        y = now.year

    counts = {
        'total': 0,
        'completed': 0,
        'ongoing': 0,
        'ongoing_analysis': 0,
        'sending_report': 0,
        'active_in_progress': 0,
        'waived': 0,
        'for_revisit': 0,
        'needs_done_date': 0,
        'alarm_critical': 0,
        'alarm_warning': 0,
        'alarm_crit_warn': 0,
        'planned_tests': 0,
        'unplanned_tests': 0,
        'validation_tests': 0,
        'other_schedule_tests': 0,
    }
    try:
        with db.engine.begin() as conn:
            if scope in ('all','all-time','alltime','overall','total'):
                base = "FROM CBM_Testing t LEFT JOIN Planner p ON p.id = t.planner_id"
                params = {}
            else:
                base = "FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id WHERE p.week_number = :w AND p.year = :y"
                params = {"w": w, "y": y}
            def scalar(sql):
                try:
                    return conn.execute(text(sql), params).scalar() or 0
                except Exception:
                    return 0
            counts['total'] = scalar("SELECT COUNT(*) " + base)
            counts['completed'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed'))"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed'))"
            )
            counts['ongoing'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND COALESCE(t.Done,0)=0 AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('ongoing','todo','')"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE COALESCE(t.Done,0)=0 AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('ongoing','todo','')"
            )
            counts['ongoing_analysis'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Status,''))) = 'ongoing analysis'"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(t.Status,''))) = 'ongoing analysis'"
            )
            counts['sending_report'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('sending','sending report','report sending','sending-report')"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(t.Status,''))) IN ('sending','sending report','report sending','sending-report')"
            )
            counts['active_in_progress'] = int(counts['ongoing']) + int(counts['ongoing_analysis']) + int(counts['sending_report'])
            counts['for_revisit'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Status,''))) = 'for revisit'"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(t.Status,''))) = 'for revisit'"
            )
            counts['waived'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Status,''))) = 'waived'"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(t.Status,''))) = 'waived'"
            )
            counts['needs_done_date'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND TRIM(COALESCE(t.Done_Tested_Date,'')) = ''"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE TRIM(COALESCE(t.Done_Tested_Date,'')) = ''"
            )
            # Schedule-type breakdown by Planner.schedule_type
            counts['planned_tests'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'planned'"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'planned'"
            )
            counts['unplanned_tests'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'unplanned'"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'unplanned'"
            )
            counts['validation_tests'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'validation'"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(p.schedule_type,''))) = 'validation'"
            )
            counts['other_schedule_tests'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(p.schedule_type,''))) NOT IN ('planned','unplanned','validation')"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(p.schedule_type,''))) NOT IN ('planned','unplanned','validation')"
            )
            counts['alarm_critical'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'critical'"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'critical'"
            )
            counts['alarm_warning'] = scalar(
                "SELECT COUNT(*) " + base +
                " AND LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'warning'"
                if 'WHERE' in base else
                "SELECT COUNT(*) " + base +
                " WHERE LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = 'warning'"
            )
            counts['alarm_crit_warn'] = int(counts['alarm_critical']) + int(counts['alarm_warning'])
    except Exception:
        pass
    return jsonify(dict(scope=('all' if scope in ('all','all-time','alltime','overall','total') else 'weekly'), week=w, year=y, **counts))


@main.route('/api/testing/kpis')
def api_testing_kpis():
    """Return KPIs for a testing type.

    Query params:
    - type: vibration|oil|thermal|ultra (optional)
    - weeks: number of weeks for trend (default 12)
    """
    t = (request.args.get('type') or '').strip().lower()
    try:
        weeks = max(4, min(52, int((request.args.get('weeks') or '12').strip())))
    except Exception:
        weeks = 12
    # Map simple type tokens to SQL LIKE patterns
    if t in ('vibration', 'va'):
        pat = '%vibration%'
    elif t in ('oil','oa'):
        pat = '%oil%'
    elif t in ('thermal','ti','thermography'):
        pat = '%thermal%'
    elif t in ('ultra','ultrasonic','uld','ultrasound'):
        pat = '%ultrasonic%'
    elif t:
        pat = '%' + t + '%'
    else:
        pat = '%'

    from datetime import datetime, date, timedelta
    now = datetime.now()
    try:
        cur_week = now.isocalendar()[1]
    except Exception:
        cur_week = int(now.strftime('%W')) or 1
    cur_year = now.year

    def scalar(conn, sql, params=None):
        try:
            return conn.execute(text(sql), params or {}).scalar() or 0
        except Exception:
            return 0

    try:
        with db.engine.begin() as conn:
            # Completed this week
            completed_sql = (
                "SELECT COUNT(*) FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id "
                "WHERE p.week_number = :w AND p.year = :y "
                "AND (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed')) "
                "AND LOWER(TRIM(COALESCE(t.Test_Type,''))) LIKE :pat"
            )
            completed = int(scalar(conn, completed_sql, {"w": cur_week, "y": cur_year, "pat": pat}))

            # Pending this week (not done)
            pending_sql = (
                "SELECT COUNT(*) FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id "
                "WHERE p.week_number = :w AND p.year = :y "
                "AND COALESCE(t.Done,0)=0 AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('ongoing','todo','') "
                "AND LOWER(TRIM(COALESCE(t.Test_Type,''))) LIKE :pat"
            )
            pending = int(scalar(conn, pending_sql, {"w": cur_week, "y": cur_year, "pat": pat}))

            # Delayed: tests not done and base date older than 7 days
            delayed_sql = (
                "WITH t AS ("
                "  SELECT t.Testing_ID, COALESCE(NULLIF(TRIM(t.Test_Date),''), NULLIF(TRIM(p.pm_date),''), NULLIF(TRIM(p.date),'')) AS base_date, COALESCE(t.Done,0) AS Done, t.Test_Type"
                "  FROM CBM_Testing t LEFT JOIN Planner p ON p.id = t.planner_id"
                "  WHERE LOWER(TRIM(COALESCE(t.Test_Type,''))) LIKE :pat"
                ") SELECT COUNT(*) FROM t WHERE (Done IS NULL OR Done=0) AND TRIM(COALESCE(base_date,''))<>'' AND CAST(julianday('now') - julianday(date(base_date)) AS INTEGER) > 7"
            )
            delayed = int(scalar(conn, delayed_sql, {"pat": pat}))

            # Trend: last N weeks completed counts
            pairs = []
            for k in range(weeks - 1, -1, -1):
                d = date.today() - timedelta(weeks=k)
                iso = d.isocalendar()
                pairs.append((iso[0], iso[1]))
            uniq = []
            seen = set()
            for y,w in pairs:
                key=(y,w)
                if key not in seen:
                    seen.add(key); uniq.append(key)
            trend = []
            labels = []
            for (yy, ww) in uniq:
                sql = (
                    "SELECT COUNT(*) FROM CBM_Testing t JOIN Planner p ON p.id = t.planner_id "
                    "WHERE p.year = :yy AND p.week_number = :ww "
                    "AND (COALESCE(t.Done,0)=1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('done','completed')) "
                    "AND LOWER(TRIM(COALESCE(t.Test_Type,''))) LIKE :pat"
                )
                cnt = int(scalar(conn, sql, {"yy": yy, "ww": ww, "pat": pat}))
                trend.append(cnt)
                labels.append(f"{yy}-W{ww:02d}")
    except Exception:
        completed = 0; pending = 0; delayed = 0; trend = []; labels = []

    return jsonify(dict(completed=completed, pending=pending, delayed=delayed, trend=trend, labels=labels, weeks=weeks, type=t))

@main.route('/technicians')
def technicians():
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'Name')
    direction = request.args.get('direction', 'asc')

    query = CBMTechnician.query
    if search:
        query = query.filter(CBMTechnician.Name.like(f'%{search}%'))
    if direction == 'desc':
        query = query.order_by(getattr(CBMTechnician, sort).desc())
    else:
        query = query.order_by(getattr(CBMTechnician, sort).asc())

    technicians = query.all()
    return render_template('technicians.html', technicians=technicians, search=search, sort=sort, direction=direction)

@main.route('/equipment')
def equipment():
    search = (request.args.get('search') or '').strip()
    eqid = (request.args.get('eqid') or '').strip()
    rows = []
    history = []
    selected_eq = None
    try:
        with db.engine.begin() as conn:
            like = f"%{search}%" if search else ''
            sql = text(
                """
                SELECT e.EquipmentID AS id,
                       e.Machine     AS machine,
                       e.Department  AS department,
                       COALESCE(e.Status,'') AS status,
                       SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,'')))='critical' THEN 1 ELSE 0 END) AS crit,
                       SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,'')))='warning' THEN 1 ELSE 0 END) AS warn,
                       SUM(CASE WHEN LOWER(TRIM(COALESCE(t.Alarm_Level,'')))='normal' THEN 1 ELSE 0 END) AS norm,
                       MAX(COALESCE(NULLIF(TRIM(t.Done_Tested_Date,''),''), NULLIF(TRIM(t.Test_Date,''),''), NULLIF(TRIM(p.pm_date,''),''))) AS last_date
                FROM Equipment e
                LEFT JOIN CBM_Testing t ON t.Equipment_ID = e.EquipmentID
                LEFT JOIN Planner p ON p.id = t.planner_id
                WHERE (:q = '' OR e.Machine LIKE :like OR e.Department LIKE :like)
                GROUP BY e.EquipmentID, e.Machine, e.Department, e.Status
                ORDER BY (crit + warn) DESC, e.Machine ASC
                """
            )
            res = conn.execute(sql, {"q": search, "like": like}).fetchall()
            for r in res:
                rows.append(dict(
                    id=r[0], machine=r[1], department=r[2], status=r[3],
                    alarm_critical=int(r[4] or 0), alarm_warning=int(r[5] or 0), alarm_normal=int(r[6] or 0),
                    last_alarm_date=r[7] or ''
                ))
            if eqid.isdigit():
                eid = int(eqid)
                # Resolve selected equipment meta
                er = conn.execute(text("SELECT EquipmentID, Machine, Department FROM Equipment WHERE EquipmentID = :id"), {"id": eid}).fetchone()
                if er:
                    selected_eq = dict(id=er[0], machine=er[1], department=er[2])
                    hsql = text(
                        """
                        SELECT t.Testing_ID, t.Test_Type,
                               COALESCE(NULLIF(TRIM(t.Status), ''), CASE WHEN COALESCE(t.Done,0)=1 THEN 'done' END, '') AS Status,
                               TRIM(COALESCE(t.Alarm_Level,'')) AS Alarm_Level,
                   TRIM(COALESCE(t.Done_Tested_Date,'')) AS Done_Tested_Date,
                   TRIM(COALESCE(t.Notes,'')) AS Notes,
                   p.week_number, p.year
                        FROM CBM_Testing t
                        LEFT JOIN Planner p ON p.id = t.planner_id
                        WHERE t.Equipment_ID = :eid
                          AND (TRIM(COALESCE(t.Alarm_Level,'')) <> ''
                               OR LOWER(TRIM(COALESCE(t.Status,''))) = 'waived')
                        ORDER BY t.Testing_ID DESC
                        LIMIT 50
                        """
                    )
                    hres = conn.execute(hsql, {"eid": eid}).fetchall()
                    for rr in hres:
                        history.append(dict(
               testing_id=rr[0], test_type=rr[1], status=rr[2] or 'todo', alarm_level=rr[3] or '',
               done_tested_date=rr[4] or '', notes=rr[5] or '', week=rr[6], year=rr[7]
                        ))
    except Exception:
        rows = []
        history = []
    return render_template('equipment.html', rows=rows, search=search, eqid=eqid, history=history, selected_eq=selected_eq)

from flask import redirect, url_for, flash

@main.route('/add_equipment', methods=['GET', 'POST'])
def add_equipment():
    if request.method == 'POST':
        name = request.form.get('name')
        department = request.form.get('department')
        status = request.form.get('status')
        if name and department and status:
            new_eq = Equipment(Machine=name, Department=department, Status=status)
            db.session.add(new_eq)
            db.session.commit()
            flash('Equipment added successfully!', 'success')
            return redirect(url_for('main.add_equipment'))
        else:
            flash('Please fill all fields.', 'error')
    return render_template('add_equipment.html')

@main.route('/add_testing', methods=['GET', 'POST'])
def add_testing():
    technicians = CBMTechnician.query.all()
    equipments = Equipment.query.all()
    if request.method == 'POST':
        technician_id = request.form.get('technician')
        equipment_id = request.form.get('equipment')
        test_date = request.form.get('test_date')
        result = request.form.get('result')
        if technician_id and equipment_id and test_date and result:
            new_test = CBMTesting(
                CBM_Technician_ID=int(technician_id),
                Equipment_ID=int(equipment_id),
                Test_Date=test_date,
                Result=result
            )
            db.session.add(new_test)
            db.session.commit()
            flash('Test record added!', 'success')
            return redirect(url_for('main.add_testing'))
        else:
            flash('Please fill all fields.', 'error')
    return render_template('add_testing.html', technicians=technicians, equipments=equipments)

@main.route('/testing_records')
def testing_records():
    technician_id = request.args.get('technician', '')
    equipment_id = request.args.get('equipment', '')
    technicians = CBMTechnician.query.all()
    equipments = Equipment.query.all()
    query = CBMTesting.query
    if technician_id:
        query = query.filter(CBMTesting.CBM_Technician_ID == int(technician_id))
    if equipment_id:
        query = query.filter(CBMTesting.Equipment_ID == int(equipment_id))
    records = query.all()
    return render_template('testing_records.html', records=records, technicians=technicians, equipments=equipments, technician_id=technician_id, equipment_id=equipment_id)

@main.route('/alarms')
def alarms():
    alarms = AlarmLevel.query.all()
    return render_template('alarms.html', alarms=alarms)


@main.route('/validation')
def validation_redirect():
    """Helper endpoint to access validation page via ?id=123.

    Redirects to /validation/<id> when a valid integer ID is provided; otherwise
    returns to home with a brief message.
    """
    from flask import redirect, url_for, flash
    id_str = (request.args.get('id') or '').strip()
    if id_str:
        flash('Single validation view is not available. Showing list instead.', 'info')
    return redirect(url_for('main.validation_results_alias'))


# Removed: single-record validation view (/validation/<id>)


# Backward/alternate path alias to support '/validation_results'
@main.route('/validation_results')
def validation_results_alias():
    """Alias: /validation_results[?id=123]

    - If id is provided and numeric: redirect to /validation/<id>.
    - If no id: render a list page of validation results grouped by alarm level.
    """
    from flask import redirect, url_for
    id_str = (request.args.get('id') or '').strip()
    if id_str.isdigit():
        flash('Single validation view is not available. Showing list instead.', 'info')

    # Filters for the list page
    week = (request.args.get('week') or '').strip()
    year = (request.args.get('year') or '').strip()
    department = (request.args.get('department') or '').strip()
    test_type_filter = (request.args.get('test_type') or '').strip()
    equipment = (request.args.get('equipment') or '').strip()
    alarm = (request.args.get('alarm') or '').strip()  # Critical|Warning|Normal
    status = (request.args.get('status') or '').strip()
    limit = (request.args.get('limit') or '200').strip()
    try:
        max_rows = max(1, min(1000, int(limit)))
    except Exception:
        max_rows = 200

    groups = { 'Critical': [], 'Warning': [], 'Normal': [], 'Unknown': [] }
    summary = { 'Critical': 0, 'Warning': 0, 'Normal': 0, 'Unknown': 0, 'Total': 0 }
    filters = dict(week=week, year=year, department=department, equipment=equipment, alarm=alarm, status=status, limit=max_rows, test_type=test_type_filter)
    try:
        with db.engine.begin() as conn:
            # Build query
            select_sql = (
                "SELECT t.Testing_ID, t.Test_Type, "
                "COALESCE(NULLIF(TRIM(t.Status), ''), CASE WHEN COALESCE(t.Done,0)=1 THEN 'done' END, '') AS Status, "
                "TRIM(COALESCE(t.Alarm_Level, '')) AS Alarm_Level, "
                "t.Notes, t.Result, t.Done_Tested_Date, t.planner_id, "
                "p.department, p.equipment, p.week_number, p.year, p.pm_date, p.schedule_type, p.proposed_target_date "
                "FROM CBM_Testing t LEFT JOIN Planner p ON p.id = t.planner_id"
            )
            clauses = []
            params = {}
            if week:
                clauses.append("p.week_number = :w")
                params['w'] = week
            if year:
                clauses.append("p.year = :y")
                params['y'] = year
            if department:
                clauses.append("p.department = :d")
                params['d'] = department
            if equipment:
                clauses.append("p.equipment = :e")
                params['e'] = equipment
            if alarm:
                clauses.append("LOWER(TRIM(COALESCE(t.Alarm_Level,''))) = :a")
                params['a'] = alarm.lower()
            if test_type_filter:
                clauses.append("TRIM(COALESCE(t.Test_Type,'')) = :tt")
                params['tt'] = test_type_filter
            if status:
                s = status.lower()
                if s in ('completed','done'):
                    clauses.append("(LOWER(TRIM(COALESCE(t.Status,''))) IN ('completed','done') OR COALESCE(t.Done,0)=1)")
                elif s in ('ongoing','todo'):
                    clauses.append("(LOWER(TRIM(COALESCE(t.Status,''))) IN ('ongoing','todo',''))")
                else:
                    clauses.append("LOWER(TRIM(COALESCE(t.Status,''))) = :s")
                    params['s'] = status
            if clauses:
                select_sql += " WHERE " + " AND ".join(clauses)
            select_sql += " ORDER BY t.Testing_ID DESC LIMIT :lim"
            params['lim'] = max_rows

            rows = conn.execute(text(select_sql), params).mappings().fetchall()
            for r in rows:
                lvl = (r.get('Alarm_Level') or '').strip().capitalize()
                if lvl not in ('Critical','Warning','Normal'):
                    lvl_key = 'Unknown'
                else:
                    # Normalize exact case
                    lvl_key = 'Critical' if lvl.lower()=='critical' else ('Warning' if lvl.lower()=='warning' else 'Normal')
                item = dict(
                    Testing_ID=r.get('Testing_ID'),
                    Test_Type=r.get('Test_Type'),
                    Status=(r.get('Status') or 'todo'),
                    Alarm_Level=(r.get('Alarm_Level') or ''),
                    Notes=r.get('Notes'),
                    Result=r.get('Result'),
                    Done_Tested_Date=r.get('Done_Tested_Date'),
                    planner_id=r.get('planner_id'),
                    department=r.get('department'),
                    equipment=r.get('equipment'),
                    week_number=r.get('week_number'),
                    year=r.get('year'),
                    pm_date=r.get('pm_date'),
                    schedule_type=r.get('schedule_type'),
                    proposed_target_date=r.get('proposed_target_date'),
                )
                groups[lvl_key].append(item)
                summary[lvl_key] += 1
                summary['Total'] += 1
    except Exception:
        pass

    # Fetch lists for filter dropdowns
    departments = []
    equipments = []
    # For Add form: only equipments that have alarms (Critical/Warning) in current list
    equipments_for_add = []
    dept_equipment_map_add = {}
    type_equipment_map_add = {}
    try:
        departments = sorted({ e.Department for e in Equipment.query.all() })
        equipments = sorted({ e.Machine for e in Equipment.query.all() })
    except Exception:
        pass

    # Build filtered equipment set from current groups (Critical + Warning only)
    try:
        eq_set = set()
        for key in ('Critical', 'Warning'):
            for r in (groups.get(key, []) or []):
                eq = (r.get('equipment') or '').strip()
                dept = (r.get('department') or '').strip()
                ttype = (r.get('Test_Type') or '').strip()
                if eq:
                    eq_set.add(eq)
                if dept and eq:
                    dept_equipment_map_add.setdefault(dept, set()).add(eq)
                if ttype and eq:
                    type_equipment_map_add.setdefault(ttype, set()).add(eq)
        # finalize structures
        equipments_for_add = sorted(eq_set)
        # convert dept->set to dept->sorted list for template
        dept_equipment_map_add = { k: sorted(list(v)) for k, v in dept_equipment_map_add.items() }
        type_equipment_map_add = { k: sorted(list(v)) for k, v in type_equipment_map_add.items() }
    except Exception:
        equipments_for_add = []
        dept_equipment_map_add = {}
        type_equipment_map_add = {}

    # Collect items scheduled as Validation (schedule_type='Validation') for a dedicated table
    validation_items = []
    try:
        for key in ('Critical', 'Warning', 'Normal', 'Unknown'):
            for r in (groups.get(key, []) or []):
                if (r.get('schedule_type') or '').strip().lower() == 'validation':
                    validation_items.append(r)
    except Exception:
        validation_items = []
    validation_count = len(validation_items)
    # Split validation items into corrected vs not corrected
    validation_corrected = []
    validation_not_corrected = []
    try:
        for r in validation_items:
            s = (r.get('Status') or '').strip().lower()
            done_date = (r.get('Done_Tested_Date') or '').strip()
            if s in ('completed', 'done') or done_date:
                validation_corrected.append(r)
            else:
                validation_not_corrected.append(r)
    except Exception:
        validation_corrected = []
        validation_not_corrected = []

    # Equipment list for filter dropdown aligned to selected testing type
    equipment_list_filter = equipments_for_add or equipments
    try:
        if test_type_filter and test_type_filter in type_equipment_map_add:
            equipment_list_filter = type_equipment_map_add.get(test_type_filter) or []
        if not equipment_list_filter:
            equipment_list_filter = equipments
    except Exception:
        equipment_list_filter = equipments

    # ...existing code...
    try:
        v_total = int(validation_count or 0)
        v_corr = int(len(validation_corrected) if validation_corrected is not None else 0)
        v_not = int(len(validation_not_corrected) if validation_not_corrected is not None else 0)
        if v_total > 0:
            v_corr_pct = round((v_corr / v_total) * 100, 1)
            v_not_pct = round((v_not / v_total) * 100, 1)
        else:
            v_corr_pct = 0.0
            v_not_pct = 0.0
    except Exception:
        v_corr_pct = 0.0
        v_not_pct = 0.0

    # Compute top-5 longest open items for Warning and Validation (not corrected)
    from datetime import datetime, date

    def _extract_base_date(item):
        # Prefer proposed_target_date, then pm_date, then Done_Tested_Date, then generic date fields
        for key in ('proposed_target_date', 'pm_date', 'Done_Tested_Date', 'date'):
            try:
                v = item.get(key) if isinstance(item, dict) else None
            except Exception:
                v = None
            if not v:
                continue
            s = str(v).strip()
            if not s:
                continue
            # try ISO parse on date portion
            try:
                iso = s[:10]
                dt = datetime.fromisoformat(iso)
                return dt.date()
            except Exception:
                try:
                    # try parsing flexible formats (fallback)
                    return datetime.strptime(s.split('T')[0].split(' ')[0], '%Y-%m-%d').date()
                except Exception:
                    continue
        return None

    def _top_n_by_age(src, n=5):
        out = []
        for r in (src or []):
            base = _extract_base_date(r)
            if not base:
                continue
            try:
                days = (date.today() - base).days
            except Exception:
                continue
            out.append({
                'equipment': r.get('equipment') or r.get('Equipment') or r.get('machine') or '',
                'test_type': (r.get('Test_Type') if isinstance(r, dict) else '') or '',
                'base_date': base.isoformat(),
                'days_open': int(days or 0),
                'planner_id': r.get('planner_id') if isinstance(r, dict) else None,
            })
        out.sort(key=lambda x: x['days_open'], reverse=True)
        return out[:n]

    # longest by days open for Warning alarm items (from groups['Warning'])
    longest_warnings = _top_n_by_age(groups.get('Warning', []), 5)
    # longest by days open for Validation items that are not corrected
    longest_validation_not_corrected = _top_n_by_age(validation_not_corrected, 5)

    return render_template(
        'validation_results.html',
        groups=groups,
        summary=summary,
        filters=filters,
        departments=departments,
        equipments=equipments,
        equipments_for_add=equipments_for_add,
        dept_equipment_map_add=dept_equipment_map_add,
        type_equipment_map_add=type_equipment_map_add,
        equipment_list_filter=equipment_list_filter,
        validation_items=validation_items,
        validation_count=validation_count,
        validation_corrected=validation_corrected,
        validation_corrected_count=len(validation_corrected),
        validation_not_corrected=validation_not_corrected,
        validation_not_corrected_count=len(validation_not_corrected),
        validation_corrected_pct=v_corr_pct,
        validation_not_corrected_pct=v_not_pct,
        longest_warnings=longest_warnings,
        longest_validation_not_corrected=longest_validation_not_corrected,
    )


@main.route('/validation_results/add', methods=['POST'])
def add_validation_task():
    """Add a single Validation-type task for a chosen Department/Equipment/Date.

    Creates (or reuses) a Planner row with schedule_type='Validation' and inserts one
    CBM_Testing entry linked via planner_id. Equipment is created if missing.
    """
    from flask import request, redirect, url_for, flash
    dept = (request.form.get('department') or '').strip()
    equip = (request.form.get('equipment') or '').strip()
    date = (request.form.get('date') or '').strip()
    test_type = (request.form.get('test_type') or '').strip()
    next_url = request.form.get('next') or url_for('main.validation_results_alias')

    if not (equip and date and test_type):
        flash('Please complete Testing Type, Equipment, and Date.', 'error')
        return redirect(next_url)
    try:
        from datetime import datetime
        d = datetime.fromisoformat(date)
        week_number = d.isocalendar()[1]
        year = d.year
        day = d.strftime('%A')
        pm_date = date
    except Exception:
        flash('Invalid date format. Please pick a valid date.', 'error')
        return redirect(next_url)

    inserted = False
    try:
        with db.engine.begin() as conn:
            # Ensure Planner exists
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS Planner (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_number INTEGER,
                    year INTEGER,
                    department TEXT,
                    equipment TEXT,
                    date TEXT,
                    day TEXT,
                    pm_date TEXT,
                    schedule_type TEXT,
                    proposed_target_date TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            ))
            # Ensure CBM_Testing has needed columns
            try:
                cbm_cols = [c[1] for c in conn.execute(text("PRAGMA table_info('CBM_Testing')"))]
                if 'planner_id' not in cbm_cols:
                    conn.execute(text("ALTER TABLE CBM_Testing ADD COLUMN planner_id INTEGER"))
                if 'Test_Type' not in cbm_cols:
                    conn.execute(text("ALTER TABLE CBM_Testing ADD COLUMN Test_Type TEXT"))
                if 'Done' not in cbm_cols:
                    conn.execute(text("ALTER TABLE CBM_Testing ADD COLUMN Done INTEGER DEFAULT 0"))
            except Exception:
                pass
            # If department not provided, try to resolve from Equipment
            if not dept and equip:
                try:
                    drow = conn.execute(text("SELECT Department FROM Equipment WHERE Machine = :m LIMIT 1"), {"m": equip}).fetchone()
                    if drow:
                        dept = drow[0]
                except Exception:
                    pass
            # Find or create Planner row for this Validation job
            row = conn.execute(text(
                "SELECT id FROM Planner WHERE department = :d AND equipment = :e AND date = :dt AND schedule_type = 'Validation' LIMIT 1"
            ), {"d": dept, "e": equip, "dt": date}).fetchone()
            if row:
                planner_id = row[0]
            else:
                conn.execute(text(
                    """
                    INSERT INTO Planner (week_number, year, department, equipment, date, day, pm_date, schedule_type)
                    VALUES (:w, :y, :d, :e, :dt, :day, :pm, 'Validation')
                    """
                ), {"w": week_number, "y": year, "d": dept, "e": equip, "dt": date, "day": day, "pm": pm_date})
                planner_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
            # Resolve EquipmentID
            eq_row = conn.execute(text("SELECT EquipmentID FROM Equipment WHERE Machine = :m LIMIT 1"), {"m": equip}).fetchone()
            equipment_id = None
            if eq_row:
                equipment_id = eq_row[0]
            else:
                if dept:
                    conn.execute(text("INSERT INTO Equipment (Department, Machine, Status) VALUES (:d, :m, 'Active')"), {"d": dept, "m": equip})
                    equipment_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
            # Insert testing task
            conn.execute(text(
                """
                INSERT INTO CBM_Testing (CBM_Technician_ID, Equipment_ID, Test_Date, Result, planner_id, Test_Type, Done)
                VALUES (NULL, :equipment_id, :test_date, NULL, :planner_id, :test_type, 0)
                """
            ), {"equipment_id": equipment_id, "test_date": date, "planner_id": planner_id, "test_type": test_type})
            inserted = True
    except Exception as e:
        flash(f'Failed to add validation task: {e}', 'error')
        return redirect(next_url)

    if inserted:
        flash('Validation task added.', 'success')
    return redirect(next_url)


@main.route('/validation_results/move_to_validation', methods=['POST'])
def move_to_validation():
    """Move a single test (by Testing_ID) into a Validation planner.

    Behavior:
    - Finds the test and its current planner meta (dept, equipment, dates).
    - Reuses an existing Validation planner for same dept/equipment/date if found; otherwise creates one.
    - Updates the test's planner_id to the Validation planner (effectively moving it).
    """
    from flask import request, redirect, url_for, flash
    tid = (request.form.get('testing_id') or '').strip()
    proposed_target_date = (request.form.get('proposed_target_date') or '').strip()
    next_url = request.form.get('next') or url_for('main.validation_results_alias')
    if not tid.isdigit():
        flash('Missing or invalid Testing ID.', 'error')
        return redirect(next_url)
    testing_id = int(tid)
    try:
        from datetime import datetime
        with db.engine.begin() as conn:
            # Ensure Planner table exists
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS Planner (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_number INTEGER,
                    year INTEGER,
                    department TEXT,
                    equipment TEXT,
                    date TEXT,
                    day TEXT,
                    pm_date TEXT,
                    schedule_type TEXT,
                    proposed_target_date TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            ))
            # Fetch test and current planner info
            row = conn.execute(text(
                """
                SELECT t.Testing_ID, t.Test_Type, t.planner_id,
                       p.department, p.equipment, p.date, p.day, p.pm_date, p.week_number, p.year
                FROM CBM_Testing t
                LEFT JOIN Planner p ON p.id = t.planner_id
                WHERE t.Testing_ID = :tid
                """
            ), {"tid": testing_id}).fetchone()
            if not row:
                flash('Test not found.', 'error')
                return redirect(next_url)
            dept = row[3] or ''
            equip = row[4] or ''
            base_date = row[5] or row[7]  # prefer Planner.date, fallback to pm_date
            if not base_date:
                # use today
                d = datetime.now()
                base_date = d.date().isoformat()
                base_day = d.strftime('%A')
                base_week = d.isocalendar()[1]
                base_year = d.year
            else:
                try:
                    d = datetime.fromisoformat(base_date)
                except Exception:
                    d = datetime.now()
                base_day = row[6] or d.strftime('%A')
                base_week = row[8] or d.isocalendar()[1]
                base_year = row[9] or d.year
            # Reuse or create Validation planner
            pr = conn.execute(text(
                "SELECT id FROM Planner WHERE department = :d AND equipment = :e AND date = :dt AND schedule_type = 'Validation' LIMIT 1"
            ), {"d": dept, "e": equip, "dt": base_date}).fetchone()
            if pr:
                val_pid = pr[0]
                # Optionally update proposed_target_date if provided
                if proposed_target_date:
                    try:
                        conn.execute(text(
                            "UPDATE Planner SET proposed_target_date = :ptd WHERE id = :pid"
                        ), {"ptd": proposed_target_date, "pid": val_pid})
                    except Exception:
                        pass
            else:
                conn.execute(text(
                    """
                    INSERT INTO Planner (week_number, year, department, equipment, date, day, pm_date, schedule_type, proposed_target_date)
                    VALUES (:w, :y, :d, :e, :dt, :day, :pm, 'Validation', :ptd)
                    """
                ), {"w": base_week, "y": base_year, "d": dept, "e": equip, "dt": base_date, "day": base_day, "pm": base_date, "ptd": proposed_target_date or None})
                val_pid = conn.execute(text("SELECT last_insert_rowid()")).scalar()
            # Move test
            conn.execute(text("UPDATE CBM_Testing SET planner_id = :pid WHERE Testing_ID = :tid"), {"pid": val_pid, "tid": testing_id})
        flash('Moved to Validation.', 'success')
    except Exception as e:
        flash(f'Failed to move: {e}', 'error')
    return redirect(next_url)


@main.route('/planner', methods=['GET', 'POST'])
def weekly_equipment_pm_planner():
    from flask import request, redirect, url_for, flash
    from sqlalchemy import text
    from app.models import db
    equipments = Equipment.query.all()
    equipment_list = [e.Machine for e in equipments]
    department_list = list({e.Department for e in equipments})
    equipment_department_map = {e.Machine: e.Department for e in equipments}
    department_equipment_map = {}
    for e in equipments:
        department_equipment_map.setdefault(e.Department, []).append(e.Machine)
    testing_types = [
        "Vibration Analysis",
        "Oil Analysis",
        "Thermal Imaging",
        "Ultrasonic Analysis",
        "Motor Dynamic Analysis",
        "Ultrasonic Leak Detection",
        "Dynamic Balancing",
        "Other"
    ]
    if request.method == 'POST':
        print('POST received')
        try:
            print('Form keys:', list(request.form.keys()))
        except Exception:
            pass
        week_number = request.form.get('week_number')
        year = request.form.get('year')
        inserted_count = 0
        try:
            with db.engine.begin() as conn:
                # Ensure required tables exist (Planner)
                conn.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS Planner (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_number INTEGER,
                        year INTEGER,
                        department TEXT,
                        equipment TEXT,
                        date TEXT,
                        day TEXT,
                        pm_date TEXT,
                        schedule_type TEXT,
                        proposed_target_date TEXT,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                    """
                ))
                # Ensure CBM_Testing has columns to support linking tests to Planner
                try:
                    cbm_cols = [c[1] for c in conn.execute(text("PRAGMA table_info('CBM_Testing')"))]
                    if 'planner_id' not in cbm_cols:
                        conn.execute(text("ALTER TABLE CBM_Testing ADD COLUMN planner_id INTEGER"))
                    if 'Test_Type' not in cbm_cols:
                        conn.execute(text("ALTER TABLE CBM_Testing ADD COLUMN Test_Type TEXT"))
                    if 'Done' not in cbm_cols:
                        conn.execute(text("ALTER TABLE CBM_Testing ADD COLUMN Done INTEGER DEFAULT 0"))
                except Exception as e_alter:
                    print('Could not ensure CBM_Testing columns:', e_alter)
                # Debug: list tables and columns
                try:
                    tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                    print('SQLite tables:', [t[0] for t in tables])
                    cols = conn.execute(text("PRAGMA table_info('Planner')"))
                    print('Planner columns:', [c[1] for c in cols])
                except Exception as e_info:
                    print('Could not inspect DB schema:', e_info)
                # Collect all row indices present in the form (robust against gaps)
                import re
                indices = set()
                for k in request.form.keys():
                    m = re.search(r'_(\d+)$', k)
                    if m:
                        indices.add(int(m.group(1)))
                for i in sorted(indices):
                    dept = request.form.get(f'department_{i}')
                    dept_new = request.form.get(f'department_new_{i}')
                    equipment = request.form.get(f'equipment_{i}')
                    equipment_new = request.form.get(f'equipment_new_{i}')
                    date = request.form.get(f'date_{i}')
                    day = request.form.get(f'day_{i}')
                    pm_date = request.form.get(f'pm_date_{i}')
                    schedule_type = request.form.get(f'schedule_type_{i}')
                    proposed_target_date = request.form.get(f'proposed_target_date_{i}')
                    testing = request.form.getlist(f'testing_{i}')
                    print(f'Row {i}: dept={dept}, dept_new={dept_new}, equipment={equipment}, equipment_new={equipment_new}, date={date}, day={day}, pm_date={pm_date}, schedule_type={schedule_type}, proposed_target_date={proposed_target_date}, testing={testing}')
                    final_dept = dept_new if dept == 'Add New' and dept_new else dept
                    final_equipment = equipment_new if equipment == 'Add New' and equipment_new else equipment
                    # Compute default week/year from first valid date if missing
                    use_week = week_number
                    use_year = year
                    if date and (not use_week or not use_year):
                        try:
                            from datetime import datetime
                            d = datetime.fromisoformat(date)
                            iso = d.isocalendar()
                            if not use_week:
                                use_week = iso[1]
                            if not use_year:
                                use_year = d.year
                        except Exception:
                            pass
                    if final_dept and final_equipment and date:
                        print(f'Inserting Planner row: {final_dept}, {final_equipment}, {date}')
                        # Insert into Planner
                        conn.execute(text("""
                            INSERT INTO Planner (week_number, year, department, equipment, date, day, pm_date, schedule_type, proposed_target_date)
                            VALUES (:week_number, :year, :department, :equipment, :date, :day, :pm_date, :schedule_type, :proposed_target_date)
                        """), dict(week_number=use_week, year=use_year, department=final_dept, equipment=final_equipment, date=date, day=day, pm_date=pm_date, schedule_type=schedule_type, proposed_target_date=proposed_target_date))
                        planner_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
                        # Resolve Equipment_ID from name; create if missing
                        eq_row = conn.execute(text("SELECT EquipmentID FROM Equipment WHERE Machine = :m LIMIT 1"), {"m": final_equipment}).fetchone()
                        equipment_id = None
                        if eq_row:
                            equipment_id = eq_row[0]
                        else:
                            if final_dept:
                                conn.execute(text("INSERT INTO Equipment (Department, Machine, Status) VALUES (:d, :m, 'Active')"), {"d": final_dept, "m": final_equipment})
                                equipment_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
                        for test_type in testing:
                            tt = (test_type or '').strip()
                            if not tt or tt.lower() == 'on':
                                continue  # skip invalid checkbox values
                            print(f'Inserting CBM_Testing test: {tt}')
                            conn.execute(text("""
                                INSERT INTO CBM_Testing (CBM_Technician_ID, Equipment_ID, Test_Date, Result, planner_id, Test_Type, Done)
                                VALUES (NULL, :equipment_id, :test_date, NULL, :planner_id, :test_type, 0)
                            """), dict(equipment_id=equipment_id, test_date=date, planner_id=planner_id, test_type=tt))
                        inserted_count += 1
                    else:
                        print(f'Skipping row {i} due to missing required fields.')
        except Exception as e:
            import traceback
            print('Error during planner insert:', e)
            traceback.print_exc()
            flash(f"Error saving planner: {e}", "error")
            return redirect(url_for('main.weekly_equipment_pm_planner'))
        print(f"Inserted {inserted_count} planner records.")
        flash(f"Successfully added {inserted_count} planner record(s) and associated tests.", "success")
        return redirect(url_for('main.weekly_equipment_pm_planner'))
    return render_template(
        'weekly_equipment_pm_planner.html',
        equipment_list=equipment_list,
        department_list=department_list,
        equipment_department_map=equipment_department_map,
        department_equipment_map=department_equipment_map,
        testing_types=testing_types
    )


@main.route('/planner_entries', methods=['GET'])
def planner_entries():
    from sqlalchemy import text
    from app.models import db
    from datetime import datetime
    equipments = Equipment.query.all()
    department_list = list({e.Department for e in equipments})
    equipment_list = list({e.Machine for e in equipments})
    # Filters
    filter_week = request.args.get('filter_week', '').strip()
    filter_year = request.args.get('filter_year', '').strip()
    if not filter_year:
        filter_year = str(datetime.now().year)
    filter_department = request.args.get('filter_department', '').strip()
    # Additional filters
    filter_equipment = request.args.get('filter_equipment', '').strip()
    filter_pm_date = request.args.get('filter_pm_date', '').strip()
    # Cascade equipment options by department, if provided
    if filter_department:
        equipment_list = sorted({e.Machine for e in equipments if e.Department == filter_department})
    else:
        equipment_list = sorted(equipment_list)
    # Type filters via abbreviations
    type_abbr_map = {
        'VA': 'Vibration Analysis',
        'OA': 'Oil Analysis',
        'TI': 'Thermal Imaging',
        'UA': 'Ultrasonic Analysis',
        'DMA': 'Motor Dynamic Analysis',
        'ULD': 'Ultrasonic Leak Detection',
        'DB': 'Dynamic Balancing',
        'Oth': 'Other',
    }
    selected_type_abbrs = request.args.getlist('type_filter')
    selected_type_full = [type_abbr_map[a] for a in selected_type_abbrs if a in type_abbr_map]
    recent_planners = []
    try:
        with db.engine.begin() as conn:
            base_sql = (
                "SELECT p.id, p.week_number, p.year, p.department, p.equipment, p.date, p.day, "
                "p.pm_date, p.schedule_type, "
                # technician update indicators
                "COALESCE((SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id), 0) AS total_tests, "
                "COALESCE((SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id AND TRIM(COALESCE(tt.Status, '')) <> ''), 0) AS status_filled, "
                "COALESCE((SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id AND (COALESCE(tt.Done,0)=1 OR LOWER(TRIM(COALESCE(tt.Status,''))) IN ('completed','done'))), 0) AS completed_count, "
                "COALESCE((SELECT COUNT(*) FROM CBM_Testing tt WHERE tt.planner_id = p.id AND TRIM(COALESCE(tt.Alarm_Level, '')) <> ''), 0) AS alarm_filled, "
                "(SELECT CASE MAX(CASE LOWER(TRIM(tt.Alarm_Level)) WHEN 'critical' THEN 3 WHEN 'warning' THEN 2 WHEN 'normal' THEN 1 ELSE 0 END) "
                "        WHEN 3 THEN 'Critical' WHEN 2 THEN 'Warning' WHEN 1 THEN 'Normal' ELSE '' END "
                " FROM CBM_Testing tt WHERE tt.planner_id = p.id) AS worst_alarm, "
                # testing types aggregation
                "COALESCE(("
                "  SELECT GROUP_CONCAT(tt.Test_Type, ', ') FROM ("
                "    SELECT DISTINCT TRIM(Test_Type) AS Test_Type FROM CBM_Testing "
                "    WHERE planner_id = p.id AND TRIM(COALESCE(Test_Type, '')) <> ''"
                "  ) tt"
                "), '') AS testing_types "
                "FROM Planner p"
            )
            clauses = []
            params = {}
            if filter_week:
                clauses.append("p.week_number = :fw")
                params['fw'] = filter_week
            if filter_year:
                clauses.append("p.year = :fy")
                params['fy'] = filter_year
            if filter_department:
                clauses.append("p.department = :fd")
                params['fd'] = filter_department
            if filter_equipment:
                clauses.append("p.equipment = :fe")
                params['fe'] = filter_equipment
            if filter_pm_date:
                clauses.append("p.pm_date = :fp")
                params['fp'] = filter_pm_date
            where_clauses = list(clauses)
            # Filter by selected testing types (any match)
            if selected_type_full:
                in_params = []
                for idx, val in enumerate(selected_type_full):
                    key = f"tt{idx}"
                    in_params.append(":" + key)
                    params[key] = val
                where_clauses.append(
                    "EXISTS (SELECT 1 FROM CBM_Testing tt WHERE tt.planner_id = p.id AND tt.Test_Type IN (" + ", ".join(in_params) + "))"
                )
            if where_clauses:
                base_sql += " WHERE " + " AND ".join(where_clauses)
            base_sql += " ORDER BY p.id DESC LIMIT 100"
            res = conn.execute(text(base_sql), params).mappings()
            recent_planners = []
            for r in res:
                testing_str = r['testing_types'] or ''
                testing_list = [x.strip() for x in testing_str.split(',') if x and x.strip()]
                pm_week = None
                try:
                    if r.get('pm_date'):
                        from datetime import datetime
                        ds = str(r.get('pm_date'))[:10]
                        dt = datetime.fromisoformat(ds).date()
                        pm_week = dt.isocalendar()[1]
                except Exception:
                    pm_week = None
                recent_planners.append(dict(
                    id=r['id'],
                    week_number=r['week_number'],
                    year=r['year'],
                    department=r['department'],
                    equipment=r['equipment'],
                    date=r['date'],
                    day=r['day'],
                    pm_date=r['pm_date'],
                    pm_week_number=pm_week,
                    schedule_type=r['schedule_type'],
                    total_tests=r['total_tests'],
                    status_filled=r['status_filled'],
                    completed_count=r['completed_count'],
                    alarm_filled=r['alarm_filled'],
                    worst_alarm=r['worst_alarm'] or '',
                    testing_types=r['testing_types'],
                    testing_types_list=testing_list,
                ))
    except Exception as _:
        recent_planners = []

    return render_template(
        'planner_entries.html',
        recent_planners=recent_planners,
        department_list=department_list,
        filter_week=filter_week,
        filter_year=filter_year,
    filter_department=filter_department,
    equipment_list=equipment_list,
    filter_equipment=filter_equipment,
    filter_pm_date=filter_pm_date
    )


@main.route('/planner/<int:planner_id>/remove_test_type', methods=['POST'])
def remove_test_type(planner_id: int):
    """Remove all tests of a specific Test_Type from a given planner entry.

    Expects form fields:
    - test_type: the human-readable test type string (e.g., 'Vibration Analysis')
    - next: optional URL to redirect back to (defaults to planner entries)
    """
    from sqlalchemy import text
    from app.models import db
    from flask import request, redirect, url_for, flash
    test_type = (request.form.get('test_type') or '').strip()
    next_url = request.form.get('next') or url_for('main.planner_entries')
    if not test_type:
        flash('Missing test type to remove.', 'error')
        return redirect(next_url)
    try:
        with db.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM CBM_Testing WHERE planner_id = :pid AND TRIM(COALESCE(Test_Type, '')) = :tt"),
                {"pid": planner_id, "tt": test_type}
            )
        flash(f"Removed '{test_type}' from planner {planner_id}.", 'success')
    except Exception as e:
        flash(f"Failed to remove '{test_type}': {e}", 'error')
    return redirect(next_url)


@main.route('/planner/add_test_type', methods=['POST'])
def add_test_type_modal():
    """Add a single test type to the given planner row via modal popup.

    Expects form fields:
    - planner_id: the planner row id
    - test_type: the human-readable test type string
    - next: optional URL to redirect back to (defaults to planner entries)
    """
    from sqlalchemy import text
    from app.models import db
    from flask import request, redirect, url_for, flash
    planner_id = request.form.get('planner_id', '').strip()
    test_type = (request.form.get('test_type') or '').strip()
    next_url = request.form.get('next') or url_for('main.planner_entries')
    if not planner_id or not planner_id.isdigit():
        flash('Missing planner id.', 'error')
        return redirect(next_url)
    pid = int(planner_id)
    if not test_type:
        flash('Please select a testing type to add.', 'error')
        return redirect(next_url)
    try:
        with db.engine.begin() as conn:
            # Check duplicate
            exists = conn.execute(
                text("SELECT 1 FROM CBM_Testing WHERE planner_id = :pid AND TRIM(COALESCE(Test_Type, '')) = :tt LIMIT 1"),
                {"pid": pid, "tt": test_type}
            ).fetchone()
            if exists:
                flash(f"'{test_type}' already exists for planner {pid}.", 'info')
                return redirect(next_url)
            # Get planner meta
            p = conn.execute(
                text("SELECT date, equipment FROM Planner WHERE id = :pid"),
                {"pid": pid}
            ).fetchone()
            test_date = p[0] if p else None
            equipment_name = p[1] if p else None
            equipment_id = None
            if equipment_name:
                row = conn.execute(
                    text("SELECT EquipmentID FROM Equipment WHERE Machine = :m LIMIT 1"),
                    {"m": equipment_name}
                ).fetchone()
                if row:
                    equipment_id = row[0]
            # Insert
            conn.execute(
                text(
                    """
                    INSERT INTO CBM_Testing (CBM_Technician_ID, Equipment_ID, Test_Date, Result, planner_id, Test_Type, Done)
                    VALUES (NULL, :equipment_id, :test_date, NULL, :planner_id, :test_type, 0)
                    """
                ),
                {
                    "equipment_id": equipment_id,
                    "test_date": test_date,
                    "planner_id": pid,
                    "test_type": test_type,
                }
            )
        flash(f"Added '{test_type}' to planner {pid}.", 'success')
    except Exception as e:
        flash(f"Failed to add '{test_type}': {e}", 'error')
    return redirect(next_url)


@main.route('/planner/<int:planner_id>/tasks')
def planner_tasks(planner_id: int):
    from sqlalchemy import text
    from app.models import db
    # Fetch tests linked to this planner via planner_id
    tasks = []
    planner_meta = None
    try:
        with db.engine.begin() as conn:
            # Get planner meta
            p = conn.execute(text("SELECT id, department, equipment, week_number, year FROM Planner WHERE id = :pid"), {"pid": planner_id}).fetchone()
            if p:
                planner_meta = dict(id=p[0], department=p[1], equipment=p[2], week_number=p[3], year=p[4])
            # Get linked tests
            sql = text(
                """
                SELECT t.Testing_ID, t.Test_Type,
                       COALESCE(t.Status, CASE WHEN t.Done=1 THEN 'done' END) AS Status,
                              t.Done, t.Alarm_Level, t.Notes, t.Test_Date, t.Done_Tested_Date
                FROM CBM_Testing t
                WHERE t.planner_id = :pid
                ORDER BY t.Testing_ID DESC
                """
            )
            res = conn.execute(sql, {"pid": planner_id})
            tasks = [
                dict(
                    Testing_ID=r[0],
                    Test_Type=r[1],
                    Status=r[2] or 'todo',
                    Done=r[3],
                    Alarm_Level=r[4],
                    Notes=r[5],
                          Test_Date=r[6],
                          Done_Tested_Date=r[7],
                ) for r in res
            ]
            # Attachments for these tests
            if tasks:
                ids = [t['Testing_ID'] for t in tasks]
                in_binds = {f"tid{i}": ids[i] for i in range(len(ids))}
                inlist = ", ".join(":" + k for k in in_binds.keys())
                att_sql = text(
                    f"SELECT testing_id, id, filename FROM CBM_Testing_Attachments WHERE testing_id IN ({inlist}) ORDER BY id DESC"
                )
                att_rows = conn.execute(att_sql, in_binds).fetchall()
                by_test = {}
                for testing_id, aid, fn in att_rows:
                    by_test.setdefault(testing_id, []).append({ 'id': aid, 'filename': fn })
                for t in tasks:
                    t['attachments'] = by_test.get(t['Testing_ID'], [])
    except Exception as _e:
        tasks = []
    return render_template('planner_tasks.html', planner_id=planner_id, planner_meta=planner_meta, tasks=tasks)