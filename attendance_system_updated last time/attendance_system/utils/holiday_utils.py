"""
holiday_utils.py
-----------------
Core logic for Holiday Management:
  - is_holiday(): the single source of truth that mark_attendance (faculty)
    and checkin (student) both call before creating any Attendance row.
  - find_duplicate(): prevents the same holiday being added twice.
  - import_holidays_from_file(): parses an uploaded CSV/XLSX annual
    calendar and adds new rows, never touching rows the Admin already
    customized (is_custom=True) and skipping exact duplicates.
"""
import csv
import io
from datetime import datetime, date

from extensions import db
from models import Holiday, ClassModel


def _parse_date_cell(value):
    """Accepts 'YYYY-MM-DD', 'DD-MM-YYYY', or 'DD/MM/YYYY'."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    value = str(value).strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def is_holiday(check_date, class_id=None):
    """Returns (True, holiday_name) if check_date is a holiday for the given
    class_id (or for everyone, if class_id is None / the holiday is global).
    Checked whenever attendance is about to be marked, so holidays are
    automatically excluded from working days -- no Attendance row (Present
    or Absent) is ever created for a holiday.
    """
    weekday = check_date.weekday()  # 0=Monday ... 6=Sunday

    query = Holiday.query.filter(
        db.or_(Holiday.class_id.is_(None), Holiday.class_id == class_id)
    )
    for h in query.all():
        if h.recurring_weekday is not None and h.recurring_weekday == weekday:
            return True, h.name
        if h.start_date and h.end_date and h.start_date <= check_date <= h.end_date:
            return True, h.name

    return False, None


def find_duplicate(name, start_date, end_date, recurring_weekday, class_id, exclude_id=None):
    """Exact-match duplicate check used by both manual add and calendar import."""
    q = Holiday.query.filter(
        Holiday.class_id == class_id,
        Holiday.recurring_weekday == recurring_weekday,
        Holiday.start_date == start_date,
        Holiday.end_date == end_date,
    )
    if exclude_id:
        q = q.filter(Holiday.id != exclude_id)
    return q.first()


def _class_id_from_name(name, class_cache):
    if not name or not name.strip():
        return None  # blank = applies to all classes/departments
    name = name.strip()
    if name not in class_cache:
        c = ClassModel.query.filter_by(name=name).first()
        class_cache[name] = c.id if c else "NOT_FOUND"
    val = class_cache[name]
    return None if val == "NOT_FOUND" else val


def _import_rows(rows, class_cache):
    added, skipped, errors = 0, 0, []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name = (row.get("name") or "").strip()
        start_raw = row.get("start_date") or row.get("date")
        end_raw = row.get("end_date") or start_raw
        class_name = row.get("class") or row.get("department")

        if not name or not start_raw:
            errors.append(f"Row {i}: missing name or date, skipped.")
            continue

        start_d = _parse_date_cell(start_raw)
        end_d = _parse_date_cell(end_raw) or start_d
        if not start_d:
            errors.append(f"Row {i}: unrecognized date '{start_raw}', skipped.")
            continue

        class_id = _class_id_from_name(class_name, class_cache)
        if class_name and class_name.strip() and class_id is None and class_name.strip() != "":
            # a class name was given but doesn't match any existing class
            errors.append(f"Row {i}: class '{class_name}' not found, treated as 'all classes'.")

        # Priority rule: never duplicate an existing row, custom or not.
        if find_duplicate(name, start_d, end_d, None, class_id):
            skipped += 1
            continue

        db.session.add(Holiday(
            name=name, start_date=start_d, end_date=end_d,
            recurring_weekday=None, class_id=class_id,
            is_custom=False, source="import",
        ))
        added += 1

    db.session.commit()
    return added, skipped, errors


def import_holidays_from_file(file_storage):
    """file_storage is a werkzeug FileStorage from request.files.
    Supports .csv and .xlsx with columns: name, start_date (or date),
    end_date (optional), class (optional, blank = all classes).
    Returns (added, skipped, errors).
    """
    filename = (file_storage.filename or "").lower()
    class_cache = {}

    if filename.endswith(".csv"):
        content = file_storage.read().decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(content))
        rows = [{(k or "").strip().lower(): v for k, v in row.items()} for row in reader]
        return _import_rows(rows, class_cache)

    if filename.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(file_storage, data_only=True)
        ws = wb.active
        header = [str(c.value).strip().lower() if c.value else "" for c in ws[1]]
        rows = []
        for excel_row in ws.iter_rows(min_row=2, values_only=True):
            row = dict(zip(header, excel_row))
            rows.append(row)
        return _import_rows(rows, class_cache)

    return 0, 0, ["Unsupported file type. Please upload a .csv or .xlsx file."]
