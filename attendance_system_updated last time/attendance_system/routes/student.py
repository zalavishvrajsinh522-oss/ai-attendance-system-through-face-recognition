import csv
import io
import os
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, Response
from flask_login import login_required, current_user

from extensions import db
from models import Student, Attendance, Timetable, ClassLocation, FaceImage, Subject
from utils.decorators import role_required
from utils.geo_utils import within_geofence
from utils import face_utils
from utils.report_utils import resolve_period, apply_date_range, summarize, PERIOD_CHOICES
from utils.holiday_utils import is_holiday

student_bp = Blueprint("student", __name__)

GRACE_MINUTES = 10  # allow check-in this many minutes before/after the scheduled slot


def _current_student():
    return Student.query.filter_by(user_id=current_user.id).first()


@student_bp.route("/dashboard")
@login_required
@role_required("student")
def dashboard():
    s = _current_student()
    total = Attendance.query.filter_by(student_id=s.id).count()
    present = Attendance.query.filter_by(student_id=s.id, status="Present").count()
    pct = round((present / total) * 100, 1) if total else 0.0
    return render_template("student/dashboard.html", student=s, total=total, present=present, pct=pct)


@student_bp.route("/profile")
@login_required
@role_required("student")
def profile():
    s = _current_student()
    return render_template("student/profile.html", student=s)


@student_bp.route("/attendance")
@login_required
@role_required("student")
def attendance():
    s = _current_student()

    period = request.args.get("period", "month")
    subject_id = request.args.get("subject_id", type=int)
    custom_start = request.args.get("start_date")
    custom_end = request.args.get("end_date")
    start, end = resolve_period(period, custom_start, custom_end)

    query = Attendance.query.filter_by(student_id=s.id)
    if subject_id:
        query = query.filter(Attendance.subject_id == subject_id)
    query = apply_date_range(query, Attendance.date, start, end)
    records = query.order_by(Attendance.date.desc(), Attendance.marked_at.desc()).all()

    total = len(records)
    present = sum(1 for r in records if r.status == "Present")
    pct = round((present / total) * 100, 1) if total else 0.0

    # Per-subject breakdown within the selected period
    subject_summary = summarize(
        records,
        key_func=lambda r: r.subject_id,
        label_func=lambda sid: (Subject.query.get(sid).name if Subject.query.get(sid) else "Unknown"),
    )

    # Subjects for the filter dropdown: all subjects for this student's class
    class_subjects = Subject.query.filter_by(class_id=s.class_id).order_by(Subject.name).all()

    return render_template(
        "student/attendance.html",
        records=records, total=total, present=present, pct=pct,
        subject_summary=subject_summary, class_subjects=class_subjects,
        selected_subject=subject_id, selected_period=period,
        start_date=custom_start or "", end_date=custom_end or "",
        range_label=f"{start} to {end}" if start and end else "All Time",
        period_choices=PERIOD_CHOICES,
    )


@student_bp.route("/attendance/export.csv")
@login_required
@role_required("student")
def export_attendance_csv():
    s = _current_student()
    period = request.args.get("period", "month")
    subject_id = request.args.get("subject_id", type=int)
    start, end = resolve_period(period, request.args.get("start_date"), request.args.get("end_date"))

    query = Attendance.query.filter_by(student_id=s.id)
    if subject_id:
        query = query.filter(Attendance.subject_id == subject_id)
    query = apply_date_range(query, Attendance.date, start, end)
    records = query.order_by(Attendance.date.desc(), Attendance.marked_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Enrollment No", "Subject", "Date", "Day", "Time Marked", "Status", "Method"])
    for r in records:
        writer.writerow([
            s.enrollment_no or "", r.subject.name, r.date.isoformat(), r.date.strftime("%A"),
            r.marked_at.strftime("%H:%M") if r.marked_at else "",
            r.status, "Face + Geo" if r.method == "face_geo" else "Manual",
        ])

    return Response(
        buffer.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=my_attendance.csv"},
    )


@student_bp.route("/timetable")
@login_required
@role_required("student")
def timetable():
    s = _current_student()
    entries = Timetable.query.filter_by(class_id=s.class_id).order_by(Timetable.day, Timetable.start_time).all()
    return render_template("student/timetable.html", entries=entries)


# ---------------- Face registration ----------------
@student_bp.route("/face", methods=["GET"])
@login_required
@role_required("student")
def face_status():
    s = _current_student()
    return render_template("student/face.html", student=s)


@student_bp.route("/face/register", methods=["POST"])
@login_required
@role_required("student")
def register_face():
    s = _current_student()
    images = request.get_json(silent=True) or {}
    frames = images.get("frames", [])
    if len(frames) < 3:
        return jsonify({"ok": False, "message": "Please capture at least 3 frames."}), 400

    faces_dir = current_app.config["FACES_DIR"]
    existing_count = FaceImage.query.filter_by(student_id=s.id).count()
    saved = 0
    for i, data_url in enumerate(frames):
        try:
            img = face_utils.decode_base64_image(data_url)
            path = face_utils.save_face_image(faces_dir, s.id, img, existing_count + i)
            if path:
                db.session.add(FaceImage(student_id=s.id, image_path=path))
                saved += 1
        except Exception:
            continue

    if saved == 0:
        return jsonify({"ok": False, "message": "No clear face detected in any frame. Try better lighting."}), 400

    s.face_registered = True
    db.session.commit()

    trained = face_utils.train_model(faces_dir, current_app.config["MODEL_PATH"])
    return jsonify({"ok": True, "saved": saved, "trained": trained})


# ---------------- Check-in (face + liveness + geofence + timetable) ----------------
def _active_timetable_entries(class_id):
    now = datetime.now()
    day_name = now.strftime("%A")
    window_start = (now - timedelta(minutes=GRACE_MINUTES)).time()
    window_end = (now + timedelta(minutes=GRACE_MINUTES)).time()

    entries = Timetable.query.filter_by(class_id=class_id, day=day_name).all()
    active = []
    for e in entries:
        if e.start_time <= window_end and e.end_time >= window_start:
            active.append(e)
    return active


@student_bp.route("/checkin", methods=["GET"])
@login_required
@role_required("student")
def checkin():
    s = _current_student()
    holiday, holiday_name = is_holiday(date.today(), s.class_id)
    if holiday:
        flash(f"Today ({holiday_name}) is a holiday -- attendance cannot be marked.", "error")
        return render_template("student/checkin.html", student=s, active_entries=[])
    active_entries = _active_timetable_entries(s.class_id)
    return render_template("student/checkin.html", student=s, active_entries=active_entries)


@student_bp.route("/checkin/submit", methods=["POST"])
@login_required
@role_required("student")
def checkin_submit():
    s = _current_student()
    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image")
    lat = payload.get("latitude")
    lng = payload.get("longitude")
    timetable_id = payload.get("timetable_id")

    if not (image_data and lat is not None and lng is not None and timetable_id):
        return jsonify({"ok": False, "message": "Missing image, location, or class period."}), 400

    holiday, holiday_name = is_holiday(date.today(), s.class_id)
    if holiday:
        return jsonify({"ok": False, "message": f"Today ({holiday_name}) is a holiday. Attendance cannot be marked."}), 400

    entry = Timetable.query.get(int(timetable_id))
    if not entry or entry.class_id != s.class_id:
        return jsonify({"ok": False, "message": "Invalid class period."}), 400

    active_entries = _active_timetable_entries(s.class_id)
    if entry.id not in [e.id for e in active_entries]:
        return jsonify({"ok": False, "message": "This class period is not currently active."}), 400

    already = Attendance.query.filter_by(
        student_id=s.id, subject_id=entry.subject_id, date=date.today()
    ).first()
    if already and already.method == "face_geo":
        return jsonify({"ok": False, "message": "Attendance already marked for this subject today."}), 400

    loc = ClassLocation.query.filter_by(class_id=s.class_id).first()
    if loc:
        if not within_geofence(float(lat), float(lng), loc.latitude, loc.longitude, loc.radius_meters):
            return jsonify({"ok": False, "message": "You are outside the allowed class location radius."}), 400

    try:
        img = face_utils.decode_base64_image(image_data)
    except Exception:
        return jsonify({"ok": False, "message": "Could not read image."}), 400

    ok, reason, liveness_ok = face_utils.verify_face(img, s.id, current_app.config["MODEL_PATH"])
    if not ok:
        return jsonify({"ok": False, "message": reason}), 400

    if already:
        already.status = "Present"
        already.method = "face_geo"
        already.latitude, already.longitude = float(lat), float(lng)
        already.timetable_id = entry.id
    else:
        db.session.add(Attendance(
            student_id=s.id, subject_id=entry.subject_id, timetable_id=entry.id,
            date=date.today(), status="Present", method="face_geo",
            latitude=float(lat), longitude=float(lng),
        ))
    db.session.commit()
    return jsonify({"ok": True, "message": "Attendance marked. Present!"})
