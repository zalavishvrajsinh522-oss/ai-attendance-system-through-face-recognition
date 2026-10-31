"""
migrations.py
--------------
This project uses db.create_all() instead of Alembic, which only creates
tables that don't exist yet -- it never adds a new column to a table that
is already there. Since we're adding `students.enrollment_no` to an
existing database, this tiny helper checks for that column and adds it
with ALTER TABLE if missing, so upgrading never touches or drops any
existing rows.

Run this AFTER db.create_all() (new tables, like `holidays`, are already
handled by create_all() itself; this is only for new columns on old
tables).
"""
from sqlalchemy import inspect, text


def ensure_schema_upgrades(db):
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    if "students" in existing_tables:
        columns = [c["name"] for c in inspector.get_columns("students")]
        if "enrollment_no" not in columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE students ADD COLUMN enrollment_no VARCHAR(50)"))
                conn.commit()
            print("Migration: added students.enrollment_no column.")
