import psycopg2
import psycopg2.extras
import streamlit as st
from contextlib import contextmanager


def _get_db_url():
    try:
        return st.secrets["DATABASE_URL"]
    except Exception:
        import os
        return os.environ.get("DATABASE_URL")


@contextmanager
def get_connection():
    conn = psycopg2.connect(_get_db_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    with get_connection() as conn:
        c = _cur(conn)
        c.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id SERIAL PRIMARY KEY,
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
                created_at TEXT DEFAULT CURRENT_DATE::text
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                att_status TEXT NOT NULL CHECK(att_status IN ('Present', 'Half-Day', 'Leave')),
                shift TEXT NOT NULL CHECK(shift IN ('Morning', 'Evening', 'Night')),
                UNIQUE(employee_id, date),
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS payroll_records (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER NOT NULL,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                days_present REAL NOT NULL,
                leaves_taken INTEGER NOT NULL,
                leave_pool REAL NOT NULL,
                daily_rate REAL NOT NULL,
                final_payout REAL NOT NULL,
                calculated_at TEXT DEFAULT NOW()::text,
                UNIQUE(employee_id, month, year),
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            )
        """)


# ── Employee CRUD ──────────────────────────────────────────────────────────────

def add_employee(name, contact, gender, doj, base_salary, bank_account="", bank_name="", ifsc_code="", default_shift="Morning"):
    with get_connection() as conn:
        _cur(conn).execute(
            """INSERT INTO employees
               (name, contact, gender, doj, base_salary, bank_account, bank_name, ifsc_code, default_shift)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (name, contact, gender, str(doj), base_salary, bank_account, bank_name, ifsc_code, default_shift),
        )


def update_employee(emp_id, **fields):
    allowed = {"name", "contact", "gender", "doj", "status", "base_salary",
               "bank_account", "bank_name", "ifsc_code", "default_shift"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    clauses = ", ".join(f"{k} = %s" for k in fields)
    with get_connection() as conn:
        _cur(conn).execute(f"UPDATE employees SET {clauses} WHERE id = %s",
                           (*fields.values(), emp_id))


def get_employees(status=None):
    with get_connection() as conn:
        c = _cur(conn)
        if status:
            c.execute("SELECT * FROM employees WHERE status = %s ORDER BY name", (status,))
        else:
            c.execute("SELECT * FROM employees ORDER BY name")
        return [dict(r) for r in c.fetchall()]


def get_employee(emp_id):
    with get_connection() as conn:
        c = _cur(conn)
        c.execute("SELECT * FROM employees WHERE id = %s", (emp_id,))
        row = c.fetchone()
    return dict(row) if row else None


def find_duplicate_employee(contact, name, exclude_id=None):
    with get_connection() as conn:
        c = _cur(conn)
        if contact and contact.strip():
            q = "SELECT id, name FROM employees WHERE contact = %s"
            params = [contact.strip()]
            if exclude_id is not None:
                q += " AND id != %s"
                params.append(exclude_id)
            c.execute(q, params)
            row = c.fetchone()
            if row:
                return {"field": "contact", "existing_id": row["id"], "existing_name": row["name"]}

        q = "SELECT id, name FROM employees WHERE LOWER(name) = LOWER(%s)"
        params = [name.strip()]
        if exclude_id is not None:
            q += " AND id != %s"
            params.append(exclude_id)
        c.execute(q, params)
        row = c.fetchone()
        if row:
            return {"field": "name", "existing_id": row["id"], "existing_name": row["name"]}

    return None


def delete_employee(emp_id):
    with get_connection() as conn:
        c = _cur(conn)
        c.execute("DELETE FROM attendance WHERE employee_id = %s", (emp_id,))
        c.execute("DELETE FROM payroll_records WHERE employee_id = %s", (emp_id,))
        c.execute("DELETE FROM employees WHERE id = %s", (emp_id,))


# ── Attendance CRUD ────────────────────────────────────────────────────────────

def upsert_attendance(employee_id, att_date, att_status, shift):
    with get_connection() as conn:
        _cur(conn).execute(
            """INSERT INTO attendance (employee_id, date, att_status, shift)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT(employee_id, date) DO UPDATE SET
                   att_status = EXCLUDED.att_status,
                   shift = EXCLUDED.shift""",
            (employee_id, str(att_date), att_status, shift),
        )


def delete_attendance(employee_id, att_date):
    with get_connection() as conn:
        _cur(conn).execute(
            "DELETE FROM attendance WHERE employee_id = %s AND date = %s",
            (employee_id, str(att_date)),
        )


def get_attendance_for_date(att_date):
    with get_connection() as conn:
        c = _cur(conn)
        c.execute("SELECT * FROM attendance WHERE date = %s", (str(att_date),))
        return [dict(r) for r in c.fetchall()]


def get_attendance_for_month(employee_id, month, year):
    with get_connection() as conn:
        c = _cur(conn)
        c.execute(
            """SELECT * FROM attendance
               WHERE employee_id = %s
                 AND EXTRACT(MONTH FROM date::date) = %s
                 AND EXTRACT(YEAR FROM date::date) = %s""",
            (employee_id, month, year),
        )
        return [dict(r) for r in c.fetchall()]


def get_attendance_for_employee_date(employee_id, att_date):
    with get_connection() as conn:
        c = _cur(conn)
        c.execute(
            "SELECT * FROM attendance WHERE employee_id = %s AND date = %s",
            (employee_id, str(att_date)),
        )
        row = c.fetchone()
    return dict(row) if row else None


def get_attendance_map(att_date):
    rows = get_attendance_for_date(att_date)
    return {r["employee_id"]: r for r in rows}


# ── Payroll CRUD ───────────────────────────────────────────────────────────────

def save_payroll(employee_id, month, year, days_present, leaves_taken,
                 leave_pool, daily_rate, final_payout):
    with get_connection() as conn:
        _cur(conn).execute(
            """INSERT INTO payroll_records
               (employee_id, month, year, days_present, leaves_taken, leave_pool, daily_rate, final_payout)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT(employee_id, month, year) DO UPDATE SET
                   days_present = EXCLUDED.days_present,
                   leaves_taken = EXCLUDED.leaves_taken,
                   leave_pool = EXCLUDED.leave_pool,
                   daily_rate = EXCLUDED.daily_rate,
                   final_payout = EXCLUDED.final_payout,
                   calculated_at = NOW()::text""",
            (employee_id, month, year, days_present, leaves_taken,
             leave_pool, daily_rate, final_payout),
        )


def get_payroll_history(employee_id):
    with get_connection() as conn:
        c = _cur(conn)
        c.execute(
            """SELECT * FROM payroll_records WHERE employee_id = %s
               ORDER BY year DESC, month DESC""",
            (employee_id,),
        )
        return [dict(r) for r in c.fetchall()]


def get_payroll_for_month(month, year):
    with get_connection() as conn:
        c = _cur(conn)
        c.execute(
            """SELECT pr.*, e.name, e.base_salary
               FROM payroll_records pr
               JOIN employees e ON e.id = pr.employee_id
               WHERE pr.month = %s AND pr.year = %s
               ORDER BY e.name""",
            (month, year),
        )
        return [dict(r) for r in c.fetchall()]
