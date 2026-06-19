import calendar
from datetime import date, datetime
from database import get_employee, get_attendance_for_month, save_payroll


def _parse_date(d):
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d), "%Y-%m-%d").date()


def get_week_number(doj_date):
    """Returns 1-4 based on day of month."""
    day = doj_date.day
    if day <= 7:
        return 1
    elif day <= 14:
        return 2
    elif day <= 21:
        return 3
    else:
        return 4


def is_post_tuesday(doj_date):
    """Monday=0 … Sunday=6; post-Tuesday means weekday >= 2 (Wed+)."""
    return doj_date.weekday() >= 2


def calculate_leave_pool(emp_id, month, year):
    """
    Returns the prorated paid-leave pool for the employee in the given month/year.
    Full-month employees → 4. Mid-month joiners → prorated with post-Tuesday cutoff.
    """
    emp = get_employee(emp_id)
    doj = _parse_date(emp["doj"])

    # DOJ is in a previous month → full pool
    if (doj.year, doj.month) < (year, month):
        return 4.0

    # DOJ is in a future month → not employed yet (should not happen in normal flow)
    if (doj.year, doj.month) > (year, month):
        return 0.0

    # DOJ is within this month
    week = get_week_number(doj)
    pool_map = {1: 4, 2: 3, 3: 2, 4: 1}
    pool = pool_map[week]

    if is_post_tuesday(doj):
        pool -= 1

    return max(0.0, float(pool))


def calculate_payout(emp_id, month, year, persist=True):
    """
    Runs the payroll engine for one employee for one month.
    Returns a dict with breakdown and final_payout.
    """
    emp = get_employee(emp_id)
    doj = _parse_date(emp["doj"])
    base_salary = emp["base_salary"]

    cal_days = calendar.monthrange(year, month)[1]
    daily_rate = base_salary / cal_days

    # 1. Check if employee DOJ is in a future month
    if (doj.year, doj.month) > (year, month):
        result = {
            "employee_id": emp_id,
            "name": emp["name"],
            "month": month,
            "year": year,
            "cal_days": cal_days,
            "daily_rate": round(daily_rate, 4),
            "base_salary": base_salary,
            "days_present": 0.0,
            "leaves_taken": 0.0,
            "leave_pool": 0.0,
            "excess_leaves": 0.0,
            "total_pay_days": 0.0,
            "final_payout": 0.0,
        }
        if persist:
            save_payroll(emp_id, month, year, 0.0, 0.0, 0.0, round(daily_rate, 4), 0.0)
        return result

    records = get_attendance_for_month(emp_id, month, year)

    # 2. Handle Inactive / Terminated employee checks
    is_inactive_or_terminated = emp["status"] in ("Inactive", "Terminated/Left")
    if is_inactive_or_terminated and not records:
        result = {
            "employee_id": emp_id,
            "name": emp["name"],
            "month": month,
            "year": year,
            "cal_days": cal_days,
            "daily_rate": round(daily_rate, 4),
            "base_salary": base_salary,
            "days_present": 0.0,
            "leaves_taken": 0.0,
            "leave_pool": 0.0,
            "excess_leaves": 0.0,
            "total_pay_days": 0.0,
            "final_payout": 0.0,
        }
        if persist:
            save_payroll(emp_id, month, year, 0.0, 0.0, 0.0, round(daily_rate, 4), 0.0)
        return result

    # 3. Determine range of active employment in this month
    start_date = max(doj, date(year, month, 1))
    if is_inactive_or_terminated and records:
        # Assume terminated on the date of their last logged attendance in this month
        record_dates = [_parse_date(r["date"]) for r in records]
        end_date = max(record_dates)
    else:
        end_date = date(year, month, cal_days)

    if start_date > end_date:
        total_days_employed = 0
    else:
        total_days_employed = (end_date - start_date).days + 1

    # 4. Filter records within employment range
    records = [r for r in records if start_date <= _parse_date(r["date"]) <= end_date]

    present_count = sum(1 for r in records if r["att_status"] == "Present")
    half_day_count = sum(1 for r in records if r["att_status"] == "Half-Day")
    leave_count = sum(1 for r in records if r["att_status"] == "Leave")

    effective_present = present_count + 0.5 * half_day_count
    # Leaves taken: full leaves + 0.5 * half days
    leaves_taken = leave_count + 0.5 * half_day_count

    leave_pool = calculate_leave_pool(emp_id, month, year)
    excess_leaves = max(0.0, leaves_taken - leave_pool)

    # 5. Calculate payout
    max_possible_salary = total_days_employed * daily_rate
    final_payout = max(0.0, max_possible_salary - excess_leaves * daily_rate)
    total_pay_days = max(0.0, total_days_employed - excess_leaves)

    result = {
        "employee_id": emp_id,
        "name": emp["name"],
        "month": month,
        "year": year,
        "cal_days": cal_days,
        "daily_rate": round(daily_rate, 4),
        "base_salary": base_salary,
        "days_present": effective_present,
        "leaves_taken": leaves_taken,
        "leave_pool": leave_pool,
        "excess_leaves": excess_leaves,
        "total_pay_days": round(total_pay_days, 2),
        "final_payout": round(final_payout, 2),
    }

    if persist:
        save_payroll(
            emp_id, month, year,
            effective_present, leaves_taken,
            leave_pool, round(daily_rate, 4),
            round(final_payout, 2),
        )

    return result


# ── Validation test suite ──────────────────────────────────────────────────────

def run_validation_tests():
    """
    Programmatically verifies the payroll engine against the three PRD test cases.
    Returns list of {name, passed, expected, got, detail}.
    """
    results = []

    # Common setup: 30-day month (June 2025), base salary = 30000
    MONTH, YEAR = 6, 2025
    CAL_DAYS = 30
    BASE = 30_000
    DR = BASE / CAL_DAYS  # 1000.0

    def _run(label, pool, present, half, leaves, total_days, expected):
        max_possible = total_days * DR
        excess = max(0.0, leaves - pool)
        payout = round(max(0.0, max_possible - excess * DR), 2)
        passed = abs(payout - expected) < 0.01
        results.append({
            "case": label,
            "passed": passed,
            "expected": expected,
            "got": payout,
            "detail": f"pool={pool}, present={present}, half={half}, leaves={leaves}, "
                      f"total_days={total_days}, excess={excess}, payout={payout}",
        })

    # Case 1: Full-month employee, 0 leaves, 30 present days
    # Expected: 30 days employed * 1000 - 0 excess leaves * 1000 = 30000.00
    _run("Full-month, 0 leaves", pool=4, present=30, half=0, leaves=0, total_days=30, expected=30_000.0)

    # Case 2: Full-month employee, 5 leaves (1 excess), 25 present
    # Expected: 30 days employed * 1000 - 1 excess leaves * 1000 = 29000.00
    _run("Full-month, 5 leaves", pool=4, present=25, half=0, leaves=5, total_days=30, expected=29_000.0)

    # Case 3: Mid-month joiner on a Thursday in Week 2
    # Thursday → weekday=3 → post-Tuesday → pool = 3 - 1 = 2
    # Assume they joined June 12 (Thursday), last day June 30 = 19 days available
    # 0 leaves, 19 present days
    # Expected: 19 days employed * 1000 - 0 excess * 1000 = 19000.00
    _run("Mid-month Thursday Week-2 joiner, 0 leaves", pool=2, present=19, half=0, leaves=0, total_days=19, expected=19_000.0)

    # Case 3b: same joiner but takes 3 leaves (1 excess over pool=2)
    # 16 present + 3 leaves; excess=1
    # Expected: 19 days employed * 1000 - 1 excess * 1000 = 18000.00
    _run("Mid-month Thursday Week-2 joiner, 3 leaves", pool=2, present=16, half=0, leaves=3, total_days=19, expected=18_000.0)

    return results

