"""
report_utils.py
---------------
Shared helpers for every attendance report (Principal / Faculty / Student):
  - resolve_period(): turns a period keyword (week/month/semester/custom/all)
    into a concrete (start_date, end_date) range.
  - summarize(): groups a list of Attendance records by any key (student,
    subject, class, week, month, day) and computes Present/Total/% for each
    group.

There is no academic-calendar table in this project, so "semester" is
approximated as the last ~6 months. If a real semester start date is later
added to the schema, only resolve_period() needs to change.
"""
from collections import defaultdict
from datetime import date, timedelta

PERIOD_CHOICES = [
    ("week", "Last 7 Days"),
    ("month", "Last 30 Days"),
    ("semester", "Last 6 Months (Semester)"),
    ("all", "All Time"),
    ("custom", "Custom Range"),
]


def resolve_period(period, custom_start=None, custom_end=None):
    """Returns (start_date, end_date) as date objects, or (None, None) for
    'all time' / no filter. custom_start/custom_end are expected as
    'YYYY-MM-DD' strings (straight from a <input type="date">) or None.
    """
    today = date.today()

    if period == "week":
        return today - timedelta(days=7), today
    if period == "month":
        return today - timedelta(days=30), today
    if period == "semester":
        return today - timedelta(days=183), today
    if period == "custom":
        start = _parse_date(custom_start)
        end = _parse_date(custom_end)
        return start, end

    return None, None  # "all" or unrecognized -> no bound


def _parse_date(value):
    if not value:
        return None
    try:
        y, m, d = map(int, value.split("-"))
        return date(y, m, d)
    except (ValueError, AttributeError):
        return None


def apply_date_range(query, date_column, start, end):
    """Applies start/end bounds (either may be None) to a SQLAlchemy query."""
    if start:
        query = query.filter(date_column >= start)
    if end:
        query = query.filter(date_column <= end)
    return query


def summarize(records, key_func, label_func):
    """Groups `records` (a list of Attendance rows) by key_func(record),
    and returns a list of dicts: {label, total, present, pct}, sorted by
    label. label_func(key) produces the human-readable group name.
    """
    buckets = defaultdict(lambda: {"total": 0, "present": 0})
    for r in records:
        key = key_func(r)
        buckets[key]["total"] += 1
        if r.status == "Present":
            buckets[key]["present"] += 1

    rows = []
    for key, v in buckets.items():
        pct = round((v["present"] / v["total"]) * 100, 1) if v["total"] else 0.0
        rows.append({"label": label_func(key), "total": v["total"], "present": v["present"], "pct": pct})

    rows.sort(key=lambda r: r["label"])
    return rows


def week_bucket(d):
    """ISO (year, week_number) tuple for grouping by week."""
    iso = d.isocalendar()
    return (iso[0], iso[1])


def week_label(key):
    year, week = key
    return f"{year}-W{week:02d}"


def month_bucket(d):
    return (d.year, d.month)


def month_label(key):
    year, month = key
    return date(year, month, 1).strftime("%B %Y")
