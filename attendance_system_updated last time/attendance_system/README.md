# Smart Attendance System (Face + Geofence)

Role-based college attendance system: **Principal (admin)**, **Faculty**, **Student**,
with face-recognition + geofence + timetable-validated self check-in for students.

## 1. Install (one time)

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

pip install -r requirements.txt
```

> If `opencv-contrib-python` fails to install on an older Python, upgrade pip first:
> `pip install --upgrade pip` then retry.

## 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set a real `SECRET_KEY`. That's it for local testing — the app
uses a local SQLite file automatically, so **no database installation is required**.

### Optional: use free Aiven MySQL instead of local SQLite
1. Create a free MySQL service at https://aiven.io/mysql
2. Copy the connection string it gives you into `.env`:
   ```
   DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:PORT/DBNAME?ssl_mode=REQUIRED
   ```
3. Restart the app — tables are created automatically in Aiven on first run.

`schema.sql` is included for reference if you ever want to inspect/import the
schema by hand, but you don't need to run it yourself.

## 3. Run

```bash
python app.py
```

Open **http://localhost:5000**

A default Principal login is created automatically on first run:
- **Username:** `admin`
- **Password:** `admin123`

**Change this password** (or create a new principal user and delete `admin`)
before using this for anything real.

## 4. Typical first-time workflow

1. Log in as `admin` (Principal)
2. Create Classes (e.g. `BCA-1`, `Diploma IT-4`)
3. Create Subjects under each class
4. Create Faculty accounts (a login is generated for each)
5. Create Student accounts, assigning each to a class
6. Go to **Timetable** → add class periods (class + subject + faculty + day + start/end time).
   This single step is also what assigns a faculty member to that subject/class —
   their dashboard automatically shows whatever appears in the timetable for them.
7. Go to **Geofence** → set each class's classroom GPS coordinates + radius (choose 100/200/300/400/500m)
9. Students log in → **Face** tab → register their face via webcam (needs 3+ clear frames)
10. During an active timetable slot, students go to **Check-in** → attendance is
    marked only if face matches, a live eye is detected, they're within the
    geofence radius, and the period is currently active.
11. Faculty can also mark attendance manually (roll-call style) from their dashboard.
12. Principal → **Reports** to view/filter all attendance.

## Notes on the anti-proxy pipeline

Face match + liveness (basic blink/eye-open check) + geofence + timetable window
together raise the bar significantly against someone holding up a photo to fake
attendance. No browser-only system can give a 100% spoof-proof guarantee (e.g.
against a played-back video) — that's true of any web-based system, not a flaw
specific to this app.

## Tech stack

- Flask + Flask-Login + Flask-SQLAlchemy
- SQLite (zero-setup local) or Aiven MySQL (free cloud) via `DATABASE_URL`
- OpenCV (Haar cascade detection + LBPH recognizer) — chosen over dlib-based
  libraries specifically because it installs via plain `pip` with no compiler
  toolchain, on Windows/Mac/Linux alike
- Bootstrap 5 (CDN) for the UI

## Project structure

```
app.py                 Flask app factory + entrypoint
config.py               DB/env configuration
extensions.py            db, login_manager singletons
models.py                All SQLAlchemy models
routes/
  auth.py                Login/logout
  principal.py            Admin CRUD, timetable (also assigns faculty), geofence, reports
  faculty.py               Assigned classes, manual attendance, history
  student.py                Profile, attendance, timetable, face reg, check-in
utils/
  face_utils.py           Face detection/training/recognition + liveness
  geo_utils.py             Haversine geofence distance check
  decorators.py            @role_required access control
templates/                Jinja2 templates (Bootstrap 5 UI)
static/                   CSS, JS, and per-student face image folders
schema.sql                Reference MySQL DDL (auto-applied by the app already)
```
