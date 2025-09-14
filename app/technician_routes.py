from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, abort
from sqlalchemy import text
from .models import db
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import mimetypes

technician = Blueprint('technician', __name__, url_prefix='/technician')


ALLOWED_EXTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.png', '.jpg', '.jpeg'}


def _ensure_schema(conn):
    """Ensure CBM_Testing has denormalized planner_* columns (idempotent)."""
    cols = [
        ("planner_week_number", "INT"),
        ("planner_year", "INT"),
        ("planner_department", "NVARCHAR(255)"),
        ("planner_equipment", "NVARCHAR(255)"),
        ("planner_pm_date", "NVARCHAR(50)"),
        ("planner_schedule_type", "NVARCHAR(100)"),
    ]
    for name, typ in cols:
        ddl = f"""
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.CBM_Testing') AND name = '{name}'
        )
        BEGIN
            ALTER TABLE dbo.CBM_Testing ADD {name} {typ} NULL;
        END
        """
        try:
            conn.execute(text(ddl))
        except Exception:
            # Ignore if lacking rights or already exists
            pass


def _row_to_task_dict(row):
    # Map SQL row to dict expected by templates
    # Safely get Done_Tested_Date regardless of row type
    try:
        done_date = row['Done_Tested_Date']
    except Exception:
        try:
            done_date = row.get('Done_Tested_Date')
        except Exception:
            done_date = None
    # Prefer actual planner_id; fall back to effective_planner_id (derived)
    try:
        pid = row.get('planner_id') if hasattr(row, 'get') else row['planner_id']
    except Exception:
        pid = None
    if not pid:
        try:
            pid = row.get('effective_planner_id') if hasattr(row, 'get') else row['effective_planner_id']
        except Exception:
            pid = None
    return dict(
        id=row['Testing_ID'],
        planner_id=pid,
        testing_type=row['Test_Type'],
        status=row['Status'] or ('done' if (row['Done'] or 0) == 1 else 'todo'),
        alarm_level=row['Alarm_Level'],
        notes=row['Notes'],
        equipment=row['equipment'],
        department=row['department'],
        week_number=row['week_number'],
        year=row['year'],
        done_tested_date=done_date,
    updated_at=(row.get('updated_at') if isinstance(row, dict) else None),
    )


def _get_attachments(conn, testing_id):
    res = conn.execute(text("SELECT id, filename, path, uploaded_at FROM CBM_Testing_Attachments WHERE testing_id = :tid ORDER BY id DESC"),
                       {"tid": testing_id})
    return [dict(id=r[0], filename=r[1], path=r[2], uploaded_at=r[3]) for r in res]


# ---------- Per-type task listing helpers and routes ----------
_TEST_TYPE_LABELS = {
    'vibration': 'Vibration Analysis',
    'oil': 'Oil Analysis',
    'thermal': 'Thermal Imaging',
    'ultrasonic': 'Ultrasonic Analysis',
    'motor_dynamic': 'Motor Dynamic Analysis',
    'leak_detection': 'Ultrasonic Leak Detection',
    'balancing': 'Dynamic Balancing',
    'other': 'Other',
}

_TEST_TYPE_SYNONYMS = {
    'vibration': ['vibration analysis', 'vibration', 'va'],
    'oil': ['oil analysis', 'oil', 'oa'],
    'thermal': ['thermal imaging', 'thermal', 'ti'],
    'ultrasonic': ['ultrasonic analysis', 'ultrasonic', 'ua'],
    'motor_dynamic': ['motor dynamic analysis', 'motor dynamic', 'dma', 'mda'],
    'leak_detection': ['ultrasonic leak detection', 'leak detection', 'uld'],
    'balancing': ['dynamic balancing', 'balancing', 'db'],
    'other': ['other', 'oth'],
}


def _fetch_tasks_for_slug(conn, slug: str, filters: dict | None = None):
    _ensure_schema(conn)
    synonyms = [s.strip().lower() for s in _TEST_TYPE_SYNONYMS.get(slug, [])]
    if not synonyms:
        return []
    binds = {f"tt{i}": v for i, v in enumerate(synonyms)}
    inlist = ", ".join(":" + k for k in binds.keys())
    base = [
        "SELECT t.Testing_ID, t.Test_Type, t.Status, t.Done, t.Alarm_Level, t.Notes, t.Done_Tested_Date, t.planner_id,",
        "       COALESCE(t.planner_id, rp.resolved_planner_id) AS effective_planner_id,",
        "       COALESCE(p.department, t.planner_department) AS department,",
        "       COALESCE(p.equipment, t.planner_equipment) AS equipment,",
        "       p.date, p.day,",
        "       COALESCE(p.pm_date, t.planner_pm_date) AS pm_date,",
        "       COALESCE(p.schedule_type, t.planner_schedule_type) AS schedule_type,",
        "       p.proposed_target_date,",
        "       COALESCE(p.week_number, t.planner_week_number) AS week_number,",
        "       COALESCE(p.year, t.planner_year) AS year",
        "FROM CBM_Testing t",
        "LEFT JOIN Planner p ON p.id = t.planner_id",
        "OUTER APPLY (",
        "  SELECT TOP 1 p2.id AS resolved_planner_id",
        "  FROM Planner p2",
        "  WHERE COALESCE(p2.week_number, 0) = COALESCE(t.planner_week_number, 0)",
        "    AND COALESCE(p2.year, 0) = COALESCE(t.planner_year, 0)",
        "    AND NULLIF(LTRIM(RTRIM(CAST(p2.department AS NVARCHAR(255)))), '') = NULLIF(LTRIM(RTRIM(CAST(t.planner_department AS NVARCHAR(255)))), '')",
        "    AND NULLIF(LTRIM(RTRIM(CAST(p2.equipment AS NVARCHAR(255)))), '') = NULLIF(LTRIM(RTRIM(CAST(t.planner_equipment AS NVARCHAR(255)))), '')",
        "    AND NULLIF(LTRIM(RTRIM(CAST(p2.pm_date AS NVARCHAR(50)))), '') = NULLIF(LTRIM(RTRIM(CAST(t.planner_pm_date AS NVARCHAR(50)))), '')",
        "  ORDER BY p2.id DESC",
        ") rp",
        # In SQL Server, TEXT/NTEXT cannot be passed to LOWER/TRIM; CAST to NVARCHAR(MAX)
        f"WHERE LTRIM(RTRIM(LOWER(CAST(t.Test_Type AS NVARCHAR(MAX))))) IN ({inlist})"
    ]
    # optional filters
    if filters:
        if filters.get('planner_id'):
            # ID takes precedence to avoid conflicts with other filters
            base.append("AND t.planner_id = :f_planner_id")
            binds['f_planner_id'] = filters['planner_id']
        else:
            if filters.get('week_number'):
                base.append("AND COALESCE(p.week_number, t.planner_week_number) = :f_week")
                binds['f_week'] = filters['week_number']
            if filters.get('department'):
                base.append("AND COALESCE(p.department, t.planner_department) LIKE :f_dept")
                binds['f_dept'] = f"%{filters['department']}%"
            if filters.get('equipment'):
                base.append("AND COALESCE(p.equipment, t.planner_equipment) LIKE :f_eqp")
                binds['f_eqp'] = f"%{filters['equipment']}%"
            if filters.get('schedule_type'):
                base.append("AND LOWER(CAST(COALESCE(p.schedule_type, t.planner_schedule_type) AS NVARCHAR(MAX))) = :f_sched")
                binds['f_sched'] = str(filters['schedule_type']).strip().lower()
        if filters.get('status'):
            st = str(filters['status']).strip().lower()
            if st in ('completed', 'done'):
                base.append("AND (COALESCE(t.Done,0) = 1 OR LOWER(TRIM(COALESCE(t.Status,''))) IN ('completed','done'))")
            elif st in ('ongoing', 'todo'):
                base.append("AND (COALESCE(t.Done,0) = 0 AND LOWER(TRIM(COALESCE(t.Status,''))) IN ('ongoing','todo',''))")
            else:
                base.append("AND LOWER(LTRIM(RTRIM(COALESCE(CAST(t.Status AS NVARCHAR(MAX)), '')))) = :f_status")
                binds['f_status'] = st
        if filters.get('alarm_level'):
            base.append("AND LOWER(CAST(t.Alarm_Level AS NVARCHAR(MAX))) = :f_alarm")
            binds['f_alarm'] = str(filters['alarm_level']).strip().lower()
    # Avoid sorting on TEXT/NTEXT; cast to NVARCHAR then TRY_CONVERT to DATE for ordering
    base.append("ORDER BY TRY_CONVERT(date, NULLIF(LTRIM(RTRIM(CAST(p.date AS NVARCHAR(50)))), '')) ASC, t.Testing_ID DESC")
    sql = text("\n".join(base))
    res = conn.execute(sql, binds).mappings()
    tasks = []
    for r in res:
        # Extend mapping to include planner fields required by templates
        task = _row_to_task_dict(r)
        task.update({
            'date': r['date'],
            'day': r['day'],
            'pm_date': r['pm_date'],
            'schedule_type': r['schedule_type'],
            'proposed_target_date': r['proposed_target_date'],
        })
        tasks.append(task)
    # Attachments: fetch for visible tasks in one query
    if tasks:
        ids = [t['id'] for t in tasks]
        # Build parameter list dynamically
        in_binds = {f"aid{i}": ids[i] for i in range(len(ids))}
        inlist = ", ".join(":" + k for k in in_binds.keys())
        att_sql = text(
            f"SELECT testing_id, id, filename FROM CBM_Testing_Attachments WHERE testing_id IN ({inlist}) ORDER BY id DESC"
        )
        atts = conn.execute(att_sql, in_binds).fetchall()
        by_test = {}
        for testing_id, att_id, filename in atts:
            by_test.setdefault(testing_id, []).append({
                'id': att_id,
                'filename': filename,
            })
        for t in tasks:
            t['attachments'] = by_test.get(t['id'], [])
            t['attachment_count'] = len(t['attachments'])
    return tasks


def _render_type_page(slug: str, template_name: str):
    label = _TEST_TYPE_LABELS.get(slug)
    if not label:
        abort(404)
    # Collect filters from query string
    f = {
        'planner_id': (request.args.get('planner_id') or '').strip() or None,
        'week_number': (request.args.get('week_number') or '').strip() or None,
        'department': (request.args.get('department') or '').strip() or None,
        'equipment': (request.args.get('equipment') or '').strip() or None,
        'pm_date': (request.args.get('pm_date') or '').strip() or None,
        'schedule_type': (request.args.get('schedule_type') or '').strip() or None,
        'status': (request.args.get('status') or '').strip() or None,
        'alarm_level': (request.args.get('alarm_level') or '').strip() or None,
    }
    with db.engine.begin() as conn:
        tasks = _fetch_tasks_for_slug(conn, slug, f)
        # Fetch dropdown data from Planner (current values used in planning)
        dep_rows = conn.execute(text(
            "SELECT DISTINCT CAST(department AS NVARCHAR(255)) AS department "
            "FROM Planner "
            "WHERE NULLIF(LTRIM(RTRIM(CAST(department AS NVARCHAR(255)))), '') IS NOT NULL "
            "ORDER BY CAST(department AS NVARCHAR(255)) ASC"
        )).fetchall()
        department_list = [r[0] for r in dep_rows]
        if f.get('department'):
            eq_rows = conn.execute(text(
                "SELECT DISTINCT CAST(equipment AS NVARCHAR(255)) AS equipment "
                "FROM Planner "
                "WHERE NULLIF(LTRIM(RTRIM(CAST(equipment AS NVARCHAR(255)))), '') IS NOT NULL "
                "AND CAST(department AS NVARCHAR(255)) = :dep "
                "ORDER BY CAST(equipment AS NVARCHAR(255)) ASC"
            ), {"dep": f['department']}).fetchall()
        else:
            eq_rows = conn.execute(text(
                "SELECT DISTINCT CAST(equipment AS NVARCHAR(255)) AS equipment "
                "FROM Planner "
                "WHERE NULLIF(LTRIM(RTRIM(CAST(equipment AS NVARCHAR(255)))), '') IS NOT NULL "
                "ORDER BY CAST(equipment AS NVARCHAR(255)) ASC"
            )).fetchall()
        equipment_list = [r[0] for r in eq_rows]
    return render_template(template_name, tasks=tasks, page_title=label, filters=f,
                           department_list=department_list, equipment_list=equipment_list)


@technician.route('/vibration')
def technician_vibration():
    return _render_type_page('vibration', 'technician/vibration.html')


@technician.route('/oil')
def technician_oil():
    return _render_type_page('oil', 'technician/oil.html')


@technician.route('/thermal')
def technician_thermal():
    return _render_type_page('thermal', 'technician/thermal.html')


@technician.route('/ultrasonic')
def technician_ultrasonic():
    return _render_type_page('ultrasonic', 'technician/ultrasonic.html')


@technician.route('/motor_dynamic')
def technician_motor_dynamic():
    return _render_type_page('motor_dynamic', 'technician/motor_dynamic.html')


@technician.route('/leak_detection')
def technician_leak_detection():
    return _render_type_page('leak_detection', 'technician/leak_detection.html')


@technician.route('/balancing')
def technician_balancing():
    return _render_type_page('balancing', 'technician/balancing.html')


@technician.route('/other')
def technician_other():
    return _render_type_page('other', 'technician/other.html')


# Dynamic category route used by planner_entries links
@technician.route('/category/<category>')
def by_category(category: str):
    # Only allow known categories
    if category not in _TEST_TYPE_LABELS:
        abort(404)
    return _render_type_page(category, f'technician/{category}.html')


@technician.route('/')
def dashboard():
    status = request.args.get('status')
    planner_id = request.args.get('planner_id')
    ttype = request.args.get('type')
    with db.engine.begin() as conn:
        _ensure_schema(conn)
        base = (
            "SELECT t.Testing_ID, t.Test_Type, t.Status, t.Done, t.Alarm_Level, t.Notes, t.Done_Tested_Date, t.planner_id, "
            "COALESCE(p.department, t.planner_department) AS department, "
            "COALESCE(p.equipment, t.planner_equipment) AS equipment, "
            "COALESCE(p.week_number, t.planner_week_number) AS week_number, "
            "COALESCE(p.year, t.planner_year) AS year "
            "FROM CBM_Testing t LEFT JOIN Planner p ON p.id = t.planner_id"
        )
        clauses = []
        params = {}
        if status:
            if status == 'done':
                clauses.append("(t.Status = :st OR t.Done = 1)")
                params['st'] = 'done'
            else:
                clauses.append("t.Status = :st")
                params['st'] = status
        if planner_id:
            clauses.append("t.planner_id = :pid")
            params['pid'] = planner_id
        if ttype:
            clauses.append("t.Test_Type LIKE :tt")
            params['tt'] = f"%{ttype}%"
        if clauses:
            base += " WHERE " + " AND ".join(clauses)
        base += " ORDER BY t.Testing_ID DESC OFFSET 0 ROWS FETCH NEXT 200 ROWS ONLY"
        res = conn.execute(text(base), params)
        tasks = []
        for r in res.mappings():
            tasks.append(_row_to_task_dict(r))
    # Render
    return render_template('technician/dashboard.html', tasks=tasks, status=status)


# Removed: /technician/tasks/<id> detail view


@technician.route('/tasks/<int:task_id>/update', methods=['POST'])
def task_update(task_id: int):
    status = (request.form.get('status') or '').strip()
    alarm_level = (request.form.get('alarm_level') or '').strip()
    notes = (request.form.get('notes') or '').strip()
    done_tested_date = (request.form.get('done_tested_date') or '').strip()
    next_url = request.form.get('next')
    with db.engine.begin() as conn:
        _ensure_schema(conn)
        # Only update provided fields
        fields = []
        params = {"tid": task_id}
        if status:
            fields.append("Status = :st")
            params['st'] = status
            # maintain Done flag
            fields.append("Done = :done")
            params['done'] = 1 if status.lower() in ('done', 'completed') else 0
        if alarm_level:
            fields.append("Alarm_Level = :al")
            params['al'] = alarm_level
        if notes or notes == '':
            fields.append("Notes = :nt")
            params['nt'] = notes
        if done_tested_date:
            fields.append("Done_Tested_Date = :dtd")
            params['dtd'] = done_tested_date
            # If a date is provided, ensure Done flag is set
            if 'Done = :done' not in ", ".join(fields):
                fields.append("Done = :done")
                params['done'] = 1
        if not fields:
                # Treat as successful no-op so user can "save" even with no remarks
                flash('Saved.')
                if next_url:
                    from urllib.parse import urlparse
                    parsed = urlparse(next_url)
                    if not parsed.netloc and not parsed.scheme:
                        return redirect(next_url)
                return redirect(url_for('technician.dashboard'))
        sql = "UPDATE CBM_Testing SET " + ", ".join(fields) + " WHERE Testing_ID = :tid"
        conn.execute(text(sql), params)
    flash('Task updated.')
    if next_url:
        # Prevent open redirect: only allow same-app paths
        from urllib.parse import urlparse
        parsed = urlparse(next_url)
        if not parsed.netloc and not parsed.scheme:
            return redirect(next_url)
    return redirect(url_for('technician.dashboard'))


def _allowed(filename: str) -> bool:
    return os.path.splitext(filename.lower())[1] in ALLOWED_EXTS


def _unique_filename(directory: str, filename: str) -> str:
    """If filename exists in directory, append ' (n)' before extension until unique."""
    name, ext = os.path.splitext(filename)
    candidate = filename
    n = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{name} ({n}){ext}"
        n += 1
    return candidate


def _resolve_attachment_path(testing_id: int, filename: str, db_path: str | None = None) -> str | None:
    """Return an existing file path for an attachment, trying common locations.

    Priority:
    1) static/uploads/testing/<testing_id>/<filename>
    2) instance/uploads/<testing_id>/<filename>
    3) db_path as stored (may be absolute from another machine)
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    # 1) Static path (new scheme)
    static_path = os.path.join(base_dir, 'static', 'uploads', 'testing', str(testing_id), filename)
    if os.path.exists(static_path):
        return static_path
    # 2) Instance path (legacy scheme)
    instance_path = os.path.join(base_dir, 'instance', 'uploads', str(testing_id), filename)
    if os.path.exists(instance_path):
        return instance_path
    # 3) DB stored path (may be absolute from previous machine)
    if db_path and os.path.exists(db_path):
        return db_path
    return None


@technician.route('/tasks/<int:task_id>/attachments', methods=['POST'])
def upload_attachments(task_id: int):
    files = request.files.getlist('files')
    if not files:
        flash('No files selected.')
        # Prefer to return to the list page if the referrer points to a technician list
        from urllib.parse import urlparse
        ref = request.referrer or ''
        parsed = urlparse(ref) if ref else None
        if parsed and parsed.path.startswith('/technician') and not parsed.path.startswith('/technician/tasks'):
            # Safe, app-internal redirect back to the list, preserve filters
            back = parsed.path + (('?' + parsed.query) if parsed.query else '')
            return redirect(back)
        return redirect(url_for('technician.dashboard'))
    # Save to static/uploads/testing/<task_id> so files sync via OneDrive and work across machines
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    upload_dir = os.path.join(base_dir, 'static', 'uploads', 'testing', str(task_id))
    os.makedirs(upload_dir, exist_ok=True)
    saved = 0
    with db.engine.begin() as conn:
        _ensure_schema(conn)
        for f in files:
            if not f or not f.filename:
                continue
            if not _allowed(f.filename):
                flash(f'Blocked: {f.filename}')
                continue
            fn = secure_filename(f.filename)
            fn = _unique_filename(upload_dir, fn)
            dest = os.path.join(upload_dir, fn)
            f.save(dest)
            conn.execute(text(
                "INSERT INTO CBM_Testing_Attachments (testing_id, filename, path, uploaded_at) VALUES (:tid, :fn, :p, :ts)"
            ), {"tid": task_id, "fn": fn, "p": dest, "ts": datetime.utcnow().isoformat()})
            saved += 1
    flash(f'Uploaded {saved} file(s).')
    # Prefer to return to the list page if the referrer points to a technician list
    from urllib.parse import urlparse
    ref = request.referrer or ''
    parsed = urlparse(ref) if ref else None
    if parsed and parsed.path.startswith('/technician') and not parsed.path.startswith('/technician/tasks'):
        back = parsed.path + (('?' + parsed.query) if parsed.query else '')
        return redirect(back)
    return redirect(url_for('technician.dashboard'))


@technician.route('/attachments/<int:attachment_id>/download')
def download_attachment(attachment_id: int):
    with db.engine.begin() as conn:
        row = conn.execute(text("SELECT testing_id, filename, path FROM CBM_Testing_Attachments WHERE id = :id"), {"id": attachment_id}).fetchone()
        if not row:
            abort(404)
        testing_id, filename, db_path = row[0], row[1], row[2]
        file_path = _resolve_attachment_path(testing_id, filename, db_path)
        if not file_path:
            abort(404)
        directory, fname = os.path.split(file_path)
        return send_from_directory(directory, fname, as_attachment=True)


@technician.route('/attachments/<int:attachment_id>/delete', methods=['POST'])
def delete_attachment(attachment_id: int):
    with db.engine.begin() as conn:
        row = conn.execute(text("SELECT testing_id, filename, path FROM CBM_Testing_Attachments WHERE id = :id"), {"id": attachment_id}).fetchone()
        if not row:
            abort(404)
        testing_id, filename, db_path = row[0], row[1], row[2]
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        static_path = os.path.join(base_dir, 'static', 'uploads', 'testing', str(testing_id), filename)
        try:
            for p in (db_path, static_path):
                if p and os.path.exists(p):
                    os.remove(p)
        finally:
            conn.execute(text("DELETE FROM CBM_Testing_Attachments WHERE id = :id"), {"id": attachment_id})
    flash('Attachment deleted.')
    # Prefer to return to the list page if the referrer points to a technician list
    from urllib.parse import urlparse
    ref = request.referrer or ''
    parsed = urlparse(ref) if ref else None
    if parsed and parsed.path.startswith('/technician') and not parsed.path.startswith('/technician/tasks'):
        back = parsed.path + (('?' + parsed.query) if parsed.query else '')
        return redirect(back)
    # Fallback to technician dashboard instead of task detail
    return redirect(url_for('technician.dashboard'))


@technician.route('/attachments/<int:attachment_id>/view')
def view_attachment(attachment_id: int):
    # Serve file inline so browser can render when supported (pdf/images)
    with db.engine.begin() as conn:
        row = conn.execute(text("SELECT testing_id, filename, path FROM CBM_Testing_Attachments WHERE id = :id"), {"id": attachment_id}).fetchone()
        if not row:
            abort(404)
        testing_id, filename, db_path = row[0], row[1], row[2]
        file_path = _resolve_attachment_path(testing_id, filename, db_path)
        if not file_path:
            abort(404)
        directory, fname = os.path.split(file_path)
        resp = send_from_directory(directory, fname, as_attachment=False)
        # Hint proper content type and inline disposition
        mtype, _ = mimetypes.guess_type(fname)
        if mtype:
            resp.mimetype = mtype
        resp.headers['Content-Disposition'] = f'inline; filename="{fname}"'
        return resp
