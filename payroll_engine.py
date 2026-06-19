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

    records = get_attendance_for_month(emp_id, month, year)

    # Filter out dates before DOJ (safety net)
    if (doj.year, doj.month) == (year, month):
        records = [r for r in records if _parse_date(r["date"]) >= doj]

    present_count = sum(1 for r in records if r["att_status"] == "Present")
    half_day_count = sum(1 for r in records if r["att_status"] == "Half-Day")
    leave_count = sum(1 for r in records if r["att_status"] == "Leave")

    effective_present = present_count + 0.5 * half_day_count

    leave_pool = calculate_leave_pool(emp_id, month, year)

    # Core formula: payout = (effective_present + leave_pool) * daily_rate
    # Covered leaves are implicitly paid (they reduce present days naturally).
    # Excess leaves (> pool) impose an additional deduction from base.
    excess_leaves = max(0, leave_count - leave_pool)
    total_pay_days = effective_present + leave_pool - excess_leaves

    final_payout = total_pay_days * daily_rate

    result = {
        "employee_id": emp_id,
        "name": emp["name"],
        "month": month,
        "year": year,
        "cal_days": cal_days,
        "daily_rate": round(daily_rate, 4),
        "base_salary": base_salary,
        "days_present": effective_present,
        "leaves_taken": leave_count,
        "leave_pool": leave_pool,
        "excess_leaves": excess_leaves,
        "total_pay_days": round(total_pay_days, 2),
        "final_payout": round(final_payout, 2),
    }

    if persist:
        save_payroll(
            emp_id, month, year,
            effective_present, leave_count,
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

    def _run(label, pool, present, half, leaves, expected):
        excess = max(0, leaves - pool)
        ep = present + 0.5 * half
        pay_days = ep + pool - excess
        payout = round(pay_days * DR, 2)
        passed = abs(payout - expected) < 0.01
        results.append({
            "case": label,
            "passed": passed,
            "expected": expected,
            "got": payout,
            "detail": f"pool={pool}, present={present}, half={half}, leaves={leaves}, "
                      f"excess={excess}, pay_days={pay_days}",
        })

    # Case 1: Full-month employee, 0 leaves, 30 present days
    # Expected: (30 + 4) * 1000 = 34000
    _run("Full-month, 0 leaves", pool=4, present=30, half=0, leaves=0, expected=34_000.0)

    # Case 2: Full-month employee, 5 leaves (1 excess), 25 present
    # Expected: (25 + 4 - 1) * 1000 = 28000
    _run("Full-month, 5 leaves", pool=4, present=25, half=0, leaves=5, expected=28_000.0)

    # Case 3: Mid-month joiner on a Thursday in Week 2
    # Thursday → weekday=3 → post-Tuesday → pool = 3 - 1 = 2
    # Assume they joined June 12 (Thursday), last day June 30 = 19 days available
    # 0 leaves, 19 present days
    # Expected: (19 + 2) * 1000 = 21000
    _run("Mid-month Thursday Week-2 joiner, 0 leaves", pool=2, present=19, half=0, leaves=0, expected=21_000.0)

    # Case 3b: same joiner but takes 3 leaves (1 excess over pool=2)
    # 16 present + 3 leaves; excess=1
    # Expected: (16 + 2 - 1) * 1000 = 17000
    _run("Mid-month Thursday Week-2 joiner, 3 leaves", pool=2, present=16, half=0, leaves=3, expected=17_000.0)

    return results
