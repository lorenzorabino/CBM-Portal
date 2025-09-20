from flask import Blueprint, render_template, request
from .models import db, AlarmLevel, CBMTechnician, CBMTesting, Equipment

# Legacy routes file (not registered). Use a distinct blueprint name to avoid collisions if imported.
legacy = Blueprint('legacy', __name__)

@legacy.route('/')
def index():
    alarms = AlarmLevel.query.all()
    technicians = CBMTechnician.query.all()
    testings = CBMTesting.query.all()
    equipments = Equipment.query.all()
    return render_template('index.html', alarms=alarms, technicians=technicians, testings=testings, equipments=equipments)

@legacy.route('/technicians')
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

@legacy.route('/equipment')
def equipment():
    search = request.args.get('search', '')
    query = Equipment.query
    if search:
        query = query.filter(
            (Equipment.Machine.like(f'%{search}%')) |
            (Equipment.Department.like(f'%{search}%'))
        )
    equipments = query.all()
    return render_template('equipment.html', equipments=equipments, search=search)

from flask import redirect, url_for, flash

@legacy.route('/add_equipment', methods=['GET', 'POST'])
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

@legacy.route('/add_testing', methods=['GET', 'POST'])
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

@legacy.route('/testing_records')
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

@legacy.route('/alarms')
def alarms():
    alarms = AlarmLevel.query.all()
    return render_template('alarms.html', alarms=alarms)


@legacy.route('/planner', methods=['GET', 'POST'])
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
        i = 0
        inserted_count = 0
        try:
            with db.engine.begin() as conn:
                # Ensure required tables exist (Planner and Planner_Test) without altering existing ORM tables
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
                while True:
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
                    if not dept and not equipment:
                        print('No more rows found, breaking loop.')
                        break
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
                            print(f'Inserting CBM_Testing test: {test_type}')
                            conn.execute(text("""
                                INSERT INTO CBM_Testing (CBM_Technician_ID, Equipment_ID, Test_Date, Result, planner_id, Test_Type, Done)
                                VALUES (NULL, :equipment_id, :test_date, NULL, :planner_id, :test_type, 0)
                            """), dict(equipment_id=equipment_id, test_date=date, planner_id=planner_id, test_type=test_type))
                        inserted_count += 1
                    else:
                        print(f'Skipping row {i} due to missing required fields.')
                    i += 1
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


@legacy.route('/planner_entries', methods=['GET'])
def planner_entries():
    from sqlalchemy import text
    from app.models import db
    from datetime import datetime
    from jinja2 import TemplateNotFound
    equipments = Equipment.query.all()
    department_list = list({e.Department for e in equipments})
    # Filters
    filter_week = request.args.get('filter_week', '').strip()
    filter_year = request.args.get('filter_year', '').strip()
    if not filter_year:
        filter_year = str(datetime.now().year)
    filter_department = request.args.get('filter_department', '').strip()
    recent_planners = []
    try:
        with db.engine.begin() as conn:
            base_sql = "SELECT id, week_number, year, department, equipment, date, day FROM Planner"
            clauses = []
            params = {}
            if filter_week:
                clauses.append("week_number = :fw")
                params['fw'] = filter_week
            if filter_year:
                clauses.append("year = :fy")
                params['fy'] = filter_year
            if filter_department:
                clauses.append("department = :fd")
                params['fd'] = filter_department
            if clauses:
                base_sql += " WHERE " + " AND ".join(clauses)
            base_sql += " ORDER BY id DESC LIMIT 100"
            res = conn.execute(text(base_sql), params)
            recent_planners = [dict(id=r[0], week_number=r[1], year=r[2], department=r[3], equipment=r[4], date=r[5], day=r[6]) for r in res]
    except Exception as _:
        recent_planners = []

    # Try rendering the standard template; if it's unavailable (e.g., OneDrive placeholder),
    # fall back to a local copy to avoid OSError [Errno 22] on read.
    try:
        return render_template(
            'planner_entries.html',
            recent_planners=recent_planners,
            department_list=department_list,
            filter_week=filter_week,
            filter_year=filter_year,
            filter_department=filter_department
        )
    except (OSError, TemplateNotFound, UnicodeDecodeError) as _e:
        return render_template(
            'planner_entries_local.html',
            recent_planners=recent_planners,
            department_list=department_list,
            filter_week=filter_week,
            filter_year=filter_year,
            filter_department=filter_department
        )