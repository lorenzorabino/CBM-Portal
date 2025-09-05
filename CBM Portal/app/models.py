from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    completed = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Task {self.title}>'

class AlarmLevel(db.Model):
    __tablename__ = 'Alarm_Level'
    Alarm_ID = db.Column(db.Integer, primary_key=True)
    Equipment_ID = db.Column(db.Integer) 
    Level = db.Column(db.Text, nullable=False) 
    Message = db.Column(db.Text) 

class CBMTechnician(db.Model):
    __tablename__ = 'CBM_Technician'
    CBM_ID = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.Text, nullable=False)
    Expertise = db.Column(db.Text)
    Email = db.Column(db.Text)

class CBMTesting(db.Model):
    __tablename__ = 'CBM_Testing'
    Testing_ID = db.Column(db.Integer, primary_key=True)
    CBM_Technician_ID = db.Column(db.Integer, db.ForeignKey('CBM_Technician.CBM_ID'))
    Equipment_ID = db.Column(db.Integer, db.ForeignKey('Equipment.EquipmentID'))
    Test_Date = db.Column(db.Text)
    Result = db.Column(db.Text)
    technician = db.relationship('CBMTechnician', backref='testings')
    equipment = db.relationship('Equipment', backref='testings')

class Equipment(db.Model):
    __tablename__ = 'Equipment'
    EquipmentID = db.Column(db.Integer, primary_key=True)
    Department = db.Column(db.Text, nullable=False)
    Machine = db.Column(db.Text, nullable=False)
    Status = db.Column(db.Text) 