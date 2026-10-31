import csv
import io
import bcrypt
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user

from extensions import db
from models import Faculty, Student, Attendance, Subject, ClassModel, Timetable, User
from utils.decorators import role_required
from utils.report_utils import resolve_period, apply_date_range, summarize, PERIOD_CHOICES
from utils.holiday_utils import is_holiday

faculty_bp = Blueprint("faculty", __name__)


def _current_faculty():
    return Faculty.query.filter_by(user_id=current_user.id).first()


# ---------------- My Account (Faculty's own email/password) ----------------
@faculty_bp.route("/settings", methods=["GET", "POST"])
@login_required
@role_required("faculty")
def settings():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_email = request.form.get("email", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not bcrypt.checkpw(current_password.encode(), current_user.password_hash.encode()):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("faculty.settings"))

        if new_password and new_password != confirm_password:
            flash("New password and confirm password do not match.", "error")
            return redirect(url_for("faculty.settings"))

        if new_email and new_email != current_user.email:
            if User.query.filter(User.email == new_email, User.id != current_user.id).first():
                flash("That email is already in use by another account.", "error")
                return redirect(url_for("faculty.settings"))
            current_user.email = new_email

        if new_password:
            if len(new_password) < 6:
                flash("Password must be at least 6 characters.", "error")
                return redirect(url_for("faculty.settings"))
            current_user.password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

        db.session.commit()
        flash("Your account was updated successfully.", "success")
        return redirect(url_for("faculty.settings"))

    return render_template("faculty/settings.html")


def _is_assigned(faculty_id, class_id, subject_id):
    """A faculty is 'assigned' to a class+subject if it appears anywhere in their timetable."""
    return Timetable.query.filter_by(
        faculty_id=faculty_id, class_id=class_id, subject_id=subject_id
    ).first() is not None


@faculty_bp.route("/dashboard")
@login_required
@role_required("faculty")
def dashboard():
    f = _current_faculty()
    assignments = []
    if f:
        entries = Timetable.query.filter_by(faculty_id=f.id).all()
        seen = {}
        for e in entries:
            key = (e.class_id, e.subject_id)
            if key not in seen:
                seen[key] = {
                    "class_id": e.class_id,
                    "subject_id": e.subject_id,
                    "class_name": e.class_.name,
                    "subject_name": e.subject.name,
                }
        assignments = list(seen.values())
    return render_template("faculty/dashboard.html", assignments=assignments)


@faculty_bp.route("/mark/<int:class_id>/<int:subject_id>", methods=["GET", "POST"])
@login_required
@role_required("faculty")
def mark_attendance(class_id, subject_id):
    f = _current_faculty()
    if not f or not _is_assigned(f.id, class_id, subject_id):
        flash("Not authorized for this class/subject.", "error")
        return redirect(url_for("faculty.dashboard"))

    class_obj = ClassModel.query.get_or_404(class_id)
    subject_obj = Subject.query.get_or_404(subject_id)
    class_students = Student.query.filter_by(class_id=class_id).all()

    holiday, holiday_name = is_holiday(date.today(), class_id)
    if holiday:
        flash(f"Today ({holiday_name}) is a holiday for {class_obj.name} -- attendance cannot be marked.", "error")
        return redirect(url_for("faculty.dashboard"))

    if request.method == "POST":
        today = date.today()
        for s in class_students:
            status = request.form.get(f"status_{s.id}", "Absent")
            existing = Attendance.query.filter_by(
                student_id=s.id, subject_id=subject_id, date=today
            ).first()
            if existing:
                existing.status = status
                existing.method = "manual"
            else:
                db.session.add(Attendance(
                    student_id=s.id, subject_id=subject_id,
                    date=today, status=status, method="manual",
                ))
        db.session.commit()
        flash("Attendance saved.", "success")
        return redirect(url_for("faculty.mark_attendance", class_id=class_id, subject_id=subject_id))

    today = date.today()
    existing_map = {
        a.student_id: a.status for a in
        Attendance.query.filter_by(subject_id=subject_id, date=today).all()
    }
    return render_template(
        "faculty/mark_attendance.html",
        class_obj=class_obj, subject_obj=subject_obj,
        students=class_students, existing_map=existing_map,
    )


@faculty_bp.route("/history/<int:class_id>/<int:subject_id>")
@login_required
@role_required("faculty")
def history(class_id, subject_id):
    f = _current_faculty()
    if not f or not _is_assigned(f.id, class_id, subject_id):
        flash("Not authorized.", "error")
        return redirect(url_for("faculty.dashboard"))

    class_obj = ClassModel.query.get_or_404(class_id)
    subject_obj = Subject.query.get_or_404(subject_id)

    period = request.args.get("period", "month")
    custom_start = request.args.get("start_date")
    custom_end = request.args.get("end_date")
    start, end = resolve_period(period, custom_start, custom_end)

    student_ids = [s.id for s in Student.query.filter_by(class_id=class_id)]
    query = Attendance.query.filter(
        Attendance.subject_id == subject_id,
        Attendance.student_id.in_(student_ids),
    )
    query = apply_date_range(query, Attendance.date, start, end)
    records = query.order_by(Attendance.date.desc(), Attendance.marked_at.desc()).all()

    # Per-student attendance % for this subject, within the selected period
    student_name_map = {s.id: s.name for s in Student.query.filter_by(class_id=class_id)}
    summary_rows = summarize(
        records,
        key_func=lambda r: r.student_id,
        label_func=lambda sid: student_name_map.get(sid, "Unknown"),
    )

    return render_template(
        "faculty/attendance_history.html",
        class_obj=class_obj, subject_obj=subject_obj, records=records,
        summary_rows=summary_rows,
        selected_period=period, start_date=custom_start or "", end_date=custom_end or "",
        range_label=f"{start} to {end}" if start and end else "All Time",
        period_choices=PERIOD_CHOICES,
    )


@faculty_bp.route("/history/<int:class_id>/<int:subject_id>/export.csv")
@login_required
@role_required("faculty")
def export_history_csv(class_id, subject_id):
    f = _current_faculty()
    if not f or not _is_assigned(f.id, class_id, subject_id):
        flash("Not authorized.", "error")
        return redirect(url_for("faculty.dashboard"))

    subject_obj = Subject.query.get_or_404(subject_id)
    period = request.args.get("period", "month")
    start, end = resolve_period(period, request.args.get("start_date"), request.args.get("end_date"))

    student_ids = [s.id for s in Student.query.filter_by(class_id=class_id)]
    query = Attendance.query.filter(
        Attendance.subject_id == subject_id, Attendance.student_id.in_(student_ids)
    )
    query = apply_date_range(query, Attendance.date, start, end)
    records = query.order_by(Attendance.date.desc(), Attendance.marked_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Enrollment No", "Student Name", "Subject", "Date", "Day", "Time Marked", "Status", "Method"])
    for r in records:
        writer.writerow([
            r.student.enrollment_no or "", r.student.name, subject_obj.name,
            r.date.isoformat(), r.date.strftime("%A"),
            r.marked_at.strftime("%H:%M") if r.marked_at else "",
            r.status, "Face + Geo" if r.method == "face_geo" else "Manual",
        ])

    return Response(
        buffer.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{subject_obj.name}.csv"},
    )
