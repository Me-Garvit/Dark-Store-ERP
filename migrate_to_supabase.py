"""
Run once to copy all data from local attendance.db → Supabase.
Usage: DATABASE_URL="postgresql://..." python migrate_to_supabase.py
"""
import sqlite3
import psycopg2
import psycopg2.extras
import os

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "attendance.db")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL environment variable before running.")


def migrate():
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    dst = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        src_cur = src.cursor()
        dst_cur = dst.cursor()

        # employees
        src_cur.execute("SELECT * FROM employees ORDER BY id")
        employees = src_cur.fetchall()
        for e in employees:
            dst_cur.execute("""
                INSERT INTO employees
                  (id, name, contact, gender, doj, status, base_salary,
                   bank_account, bank_name, ifsc_code, default_shift, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, (e["id"], e["name"], e["contact"], e["gender"], e["doj"],
                  e["status"], e["base_salary"], e["bank_account"],
                  e["bank_name"], e["ifsc_code"], e["default_shift"], e["created_at"]))
        print(f"Migrated {len(employees)} employees")

        # reset serial so new inserts don't conflict
        if employees:
            max_id = max(e["id"] for e in employees)
            dst_cur.execute(f"SELECT setval('employees_id_seq', {max_id})")

        # attendance
        src_cur.execute("SELECT * FROM attendance ORDER BY id")
        records = src_cur.fetchall()
        for r in records:
            dst_cur.execute("""
                INSERT INTO attendance (id, employee_id, date, att_status, shift)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, (r["id"], r["employee_id"], r["date"], r["att_status"], r["shift"]))
        print(f"Migrated {len(records)} attendance records")

        if records:
            max_id = max(r["id"] for r in records)
            dst_cur.execute(f"SELECT setval('attendance_id_seq', {max_id})")

        # payroll_records
        src_cur.execute("SELECT * FROM payroll_records ORDER BY id")
        payrolls = src_cur.fetchall()
        for p in payrolls:
            dst_cur.execute("""
                INSERT INTO payroll_records
                  (id, employee_id, month, year, days_present, leaves_taken,
                   leave_pool, daily_rate, final_payout, calculated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, (p["id"], p["employee_id"], p["month"], p["year"],
                  p["days_present"], p["leaves_taken"], p["leave_pool"],
                  p["daily_rate"], p["final_payout"], p["calculated_at"]))
        print(f"Migrated {len(payrolls)} payroll records")

        if payrolls:
            max_id = max(p["id"] for p in payrolls)
            dst_cur.execute(f"SELECT setval('payroll_records_id_seq', {max_id})")

        dst.commit()
        print("Migration complete.")

    except Exception as e:
        dst.rollback()
        raise e
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    migrate()
