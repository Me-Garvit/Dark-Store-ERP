import sqlite3
import os
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "attendance.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                contact TEXT,
                gender TEXT CHECK(gender IN ('Male', 'Female', 'Other')),
                doj TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active'
                    CHECK(status IN ('Active', 'Inactive', 'Terminated/Left')),
                base_salary REAL NOT NULL,
                bank_account TEXT,
                bank_name TEXT,
                ifsc_code TEXT,
                default_shift TEXT NOT NULL DEFAULT 'Morning'
                    CHECK(default_shift IN ('Morning', 'Evening', 'Night')),
                created_at TEXT DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                att_status TEXT NOT NULL CHECK(att_status IN ('Present', 'Half-Day', 'Leave')),
                shift TEXT NOT NULL CHECK(shift IN ('Morning', 'Evening', 'Night')),
                UNIQUE(employee_id, date),
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            );

            CREATE TABLE IF NOT EXISTS payroll_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                days_present REAL NOT NULL,
                leaves_taken INTEGER NOT NULL,
                leave_pool REAL NOT NULL,
                daily_rate REAL NOT NULL,
                final_payout REAL NOT NULL,
                calculated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(employee_id, month, year),
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            );
        """)


# ── Employee CRUD ──────────────────────────────────────────────────────────────

def add_employee(name, contact, gender, doj, base_salary, bank_account="", bank_name="", ifsc_code="", default_shift="Morning"):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO employees
               (name, contact, gender, doj, base_salary, bank_account, bank_name, ifsc_code, default_shift)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, contact, gender, str(doj), base_salary, bank_account, bank_name, ifsc_code, default_shift),
        )


def update_employee(emp_id, **fields):
    allowed = {"name", "contact", "gender", "doj", "status", "base_salary",
               "bank_account", "bank_name", "ifsc_code", "default_shift"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    clauses = ", ".join(f"{k} = ?" for k in fields)
    with get_connection() as conn:
        conn.execute(f"UPDATE employees SET {clauses} WHERE id = ?",
                     (*fields.values(), emp_id))


def get_employees(status=None):
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM employees WHERE status = ? ORDER BY name", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_employee(emp_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()
    return dict(row) if row else None


def find_duplicate_employee(contact, name, exclude_id=None):
    """
    Returns a dict describing the first duplicate found, or None.
    Primary check: contact number. Secondary check: name (case-insensitive).
    exclude_id skips a specific employee (for edit-time checks).
    """
    with get_connection() as conn:
        # Primary: same contact number (only when contact is non-empty)
        if contact and contact.strip():
            q = "SELECT id, name FROM employees WHERE contact = ?"
            params = [contact.strip()]
            if exclude_id is not None:
                q += " AND id != ?"
                params.append(exclude_id)
            row = conn.execute(q, params).fetchone()
            if row:
                return {"field": "contact", "existing_id": row["id"], "existing_name": row["name"]}

        # Secondary: same name (case-insensitive)
        q = "SELECT id, name FROM employees WHERE LOWER(name) = LOWER(?)"
        params = [name.strip()]
        if exclude_id is not None:
            q += " AND id != ?"
            params.append(exclude_id)
        row = conn.execute(q, params).fetchone()
        if row:
            return {"field": "name", "existing_id": row["id"], "existing_name": row["name"]}

    return None


def delete_employee(emp_id):
    """Hard-deletes the employee and all linked attendance/payroll records."""
    with get_connection() as conn:
        conn.execute("DELETE FROM attendance WHERE employee_id = ?", (emp_id,))
        conn.execute("DELETE FROM payroll_records WHERE employee_id = ?", (emp_id,))
        conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))


# ── Attendance CRUD ────────────────────────────────────────────────────────────

def upsert_attendance(employee_id, att_date, att_status, shift):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO attendance (employee_id, date, att_status, shift)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(employee_id, date) DO UPDATE SET
                   att_status = excluded.att_status,
                   shift = excluded.shift""",
            (employee_id, str(att_date), att_status, shift),
        )


def delete_attendance(employee_id, att_date):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM attendance WHERE employee_id = ? AND date = ?",
            (employee_id, str(att_date)),
        )


def get_attendance_for_date(att_date):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM attendance WHERE date = ?", (str(att_date),)
        ).fetchall()
    return [dict(r) for r in rows]


def get_attendance_for_month(employee_id, month, year):
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM attendance
               WHERE employee_id = ?
                 AND strftime('%m', date) = ?
                 AND strftime('%Y', date) = ?""",
            (employee_id, f"{month:02d}", str(year)),
        ).fetchall()
    return [dict(r) for r in rows]


def get_attendance_for_employee_date(employee_id, att_date):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM attendance WHERE employee_id = ? AND date = ?",
            (employee_id, str(att_date)),
        ).fetchone()
    return dict(row) if row else None


def get_attendance_map(att_date):
    """Returns {employee_id: {att_status, shift}} for a given date."""
    rows = get_attendance_for_date(att_date)
    return {r["employee_id"]: r for r in rows}


# ── Payroll CRUD ───────────────────────────────────────────────────────────────

def save_payroll(employee_id, month, year, days_present, leaves_taken,
                 leave_pool, daily_rate, final_payout):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO payroll_records
               (employee_id, month, year, days_present, leaves_taken, leave_pool, daily_rate, final_payout)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(employee_id, month, year) DO UPDATE SET
                   days_present = excluded.days_present,
                   leaves_taken = excluded.leaves_taken,
                   leave_pool = excluded.leave_pool,
                   daily_rate = excluded.daily_rate,
                   final_payout = excluded.final_payout,
                   calculated_at = datetime('now')""",
            (employee_id, month, year, days_present, leaves_taken,
             leave_pool, daily_rate, final_payout),
        )


def get_payroll_history(employee_id):
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM payroll_records WHERE employee_id = ?
               ORDER BY year DESC, month DESC""",
            (employee_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_payroll_for_month(month, year):
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT pr.*, e.name, e.base_salary
               FROM payroll_records pr
               JOIN employees e ON e.id = pr.employee_id
               WHERE pr.month = ? AND pr.year = ?
               ORDER BY e.name""",
            (month, year),
        ).fetchall()
    return [dict(r) for r in rows]
