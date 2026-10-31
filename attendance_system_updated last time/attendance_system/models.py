from datetime import datetime
from flask_login import UserMixin
from extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # principal / faculty / student
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    faculty_profile = db.relationship("Faculty", backref="user", uselist=False)
    student_profile = db.relationship("Student", backref="user", uselist=False)


class ClassModel(db.Model):
    __tablename__ = "classes"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

    subjects = db.relationship("Subject", backref="class_", cascade="all, delete-orphan")
    students = db.relationship("Student", backref="class_", cascade="all, delete-orphan")
    location = db.relationship("ClassLocation", backref="class_", uselist=False,
                                cascade="all, delete-orphan")


class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)


class Faculty(db.Model):
    __tablename__ = "faculty"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    enrollment_no = db.Column(db.String(50), unique=True, nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    face_registered = db.Column(db.Boolean, default=False)

    face_images = db.relationship("FaceImage", backref="student", cascade="all, delete-orphan")
    attendance_records = db.relationship("Attendance", backref="student", cascade="all, delete-orphan")


class FaceImage(db.Model):
    __tablename__ = "face_images"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Timetable(db.Model):
    __tablename__ = "timetable"
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey("faculty.id"), nullable=False)
    day = db.Column(db.String(10), nullable=False)  # Monday..Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    class_ = db.relationship("ClassModel", backref="timetable_entries")
    subject = db.relationship("Subject", backref="timetable_entries")
    faculty = db.relationship("Faculty", backref="timetable_entries")


class ClassLocation(db.Model):
    __tablename__ = "locations"
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False, unique=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    radius_meters = db.Column(db.Float, default=100)


class Holiday(db.Model):
    """A holiday/vacation entry.

    - A single-day holiday has start_date == end_date.
    - A vacation range (summer break, festival break) has start_date < end_date.
    - A recurring weekly holiday (e.g. every Sunday) sets recurring_weekday
      instead of dates, and has no start/end date.
    - class_id = None means the holiday applies to every class/department;
      otherwise it applies only to that one class.
    - is_custom marks a row the Admin added/edited by hand. A calendar
      import never overwrites or deletes an is_custom row -- this is the
      "priority rule" that protects Admin's manual changes.
    """
    __tablename__ = "holidays"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    recurring_weekday = db.Column(db.Integer, nullable=True)  # 0=Monday ... 6=Sunday
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    is_custom = db.Column(db.Boolean, default=True)
    source = db.Column(db.String(20), default="manual")  # 'manual' or 'import'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class_ = db.relationship("ClassModel", backref="holidays")


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    timetable_id = db.Column(db.Integer, db.ForeignKey("timetable.id"), nullable=True)
    date = db.Column(db.Date, nullable=False)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(10), nullable=False)  # Present / Absent
    method = db.Column(db.String(20), default="manual")  # manual / face_geo
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    subject = db.relationship("Subject", backref="attendance_records")
