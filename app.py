import streamlit as st
import pandas as pd
import calendar
from datetime import date, datetime, timedelta

import database as db
import payroll_engine as pe
import auth

st.set_page_config(page_title="Dark Store Attendance Tracker", layout="wide")

if not auth.check_auth():
    auth.login_page()
    st.stop()

db.init_db()


# ── Calendar HTML builder ──────────────────────────────────────────────────────

def build_attendance_calendar_html(emp_id, month, year, doj):
    records = db.get_attendance_for_month(emp_id, month, year)
    att_map = {r["date"]: r for r in records}

    today     = date.today()
    num_days  = calendar.monthrange(year, month)[1]
    start_col = date(year, month, 1).weekday()  # Monday = 0

    SHIFT_COLOR = {"Morning": "#2563eb", "Evening": "#7c3aed", "Night": "#374151"}
    SHIFT_ABBR  = {"Morning": "MOR", "Evening": "EVE", "Night": "NGT"}

    cells = ""
    col = start_col
    for _ in range(start_col):
        cells += '<td class="cal-empty"></td>'

    for day in range(1, num_days + 1):
        d        = date(year, month, day)
        ds       = str(d)
        is_today = d == today
        pre_doj  = d < doj
        future   = d > today
        border   = "2px solid #60a5fa" if is_today else "1px solid #2a2a2a"

        if pre_doj:
            cells += (
                f'<td class="cal-cell" style="background:#111;border:{border};opacity:0.45;">'
                f'<div class="cal-day" style="color:#555">{day}</div>'
                f'<div class="cal-label" style="color:#444">N/A</div></td>'
            )
        elif ds in att_map:
            rec    = att_map[ds]
            status = rec["att_status"]
            shift  = rec["shift"]
            sc     = SHIFT_COLOR.get(shift, "#374151")
            sa     = SHIFT_ABBR.get(shift, shift[:3].upper())
            bg, lc = {
                "Present":  ("#14532d", "#4ade80"),
                "Half-Day": ("#451a03", "#fbbf24"),
                "Leave":    ("#450a0a", "#f87171"),
            }.get(status, ("#1a1a1a", "#aaa"))
            cells += (
                f'<td class="cal-cell" style="background:{bg};border:{border};">'
                f'<div class="cal-day">{day}</div>'
                f'<div class="cal-label" style="color:{lc}">{status}</div>'
                f'<span class="cal-shift" style="background:{sc};">{sa}</span></td>'
            )
        else:
            dimmed = "#1c1c1c" if future else "#1f1f1f"
            dc     = "#555" if future else "#666"
            cells += (
                f'<td class="cal-cell" style="background:{dimmed};border:{border};">'
                f'<div class="cal-day" style="color:{dc}">{day}</div></td>'
            )

        col += 1
        if col == 7 and day != num_days:
            cells += "</tr><tr>"
            col = 0

    for _ in range((7 - col) % 7):
        cells += '<td class="cal-empty"></td>'

    present = sum(1 for r in records if r["att_status"] == "Present")
    halfday = sum(1 for r in records if r["att_status"] == "Half-Day")
    leave   = sum(1 for r in records if r["att_status"] == "Leave")

    return f"""
<style>
  .att-wrap {{ overflow-x: auto; }}
  .att-table {{ border-collapse: collapse; width: 100%; min-width: 420px; }}
  .att-table th {{
    text-align: center; padding: 8px 4px;
    background: #1e293b; color: #94a3b8;
    font-size: 12px; letter-spacing: .05em;
  }}
  .cal-cell, .cal-empty {{
    text-align: center; padding: 6px 2px;
    min-width: 50px; height: 68px; vertical-align: top;
  }}
  .cal-empty {{ background: #111; border: 1px solid #1e1e1e; }}
  .cal-day {{ font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 3px; }}
  .cal-label {{ font-size: 10px; font-weight: 600; margin-bottom: 3px; }}
  .cal-shift {{
    font-size: 9px; font-weight: 700; color: #fff;
    border-radius: 3px; padding: 1px 4px; letter-spacing: .04em;
  }}
  .att-summary {{ display:flex; gap:16px; margin-top:10px; font-size:13px; flex-wrap:wrap; }}
  .att-badge {{ padding: 3px 10px; border-radius: 4px; font-weight:600; }}
</style>
<div class="att-wrap">
  <table class="att-table">
    <thead><tr>
      <th>MON</th><th>TUE</th><th>WED</th><th>THU</th><th>FRI</th><th>SAT</th><th>SUN</th>
    </tr></thead>
    <tbody><tr>{cells}</tr></tbody>
  </table>
  <div class="att-summary">
    <span class="att-badge" style="background:#14532d;color:#4ade80">Present: {present}</span>
    <span class="att-badge" style="background:#451a03;color:#fbbf24">Half-Day: {halfday}</span>
    <span class="att-badge" style="background:#450a0a;color:#f87171">Leave: {leave}</span>
    <span class="att-badge" style="background:#1e293b;color:#94a3b8">Logged: {len(records)}</span>
  </div>
</div>
"""

# ── Sidebar navigation ─────────────────────────────────────────────────────────
PAGES = ["Employee Directory", "Daily Attendance Logger", "Payroll Calculator", "Validation Tests"]
page = st.sidebar.radio("Navigation", PAGES)
st.sidebar.divider()
if st.sidebar.button("Logout", use_container_width=True):
    auth.logout()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — EMPLOYEE DIRECTORY
# ══════════════════════════════════════════════════════════════════════════════
if page == "Employee Directory":
    st.title("Employee Directory")

    tab_active, tab_inactive, tab_terminated, tab_add = st.tabs(
        ["Active", "Inactive", "Terminated / Left", "Add Employee"]
    )

    def employee_card(emp):
        eid = emp["id"]
        doj_date = datetime.strptime(emp["doj"], "%Y-%m-%d").date()

        with st.expander(f"#{eid}  {emp['name']}  —  {emp['status']}"):
            t_profile, t_attendance, t_history = st.tabs(
                ["Profile & Edit", "Attendance Calendar", "Payout History"]
            )

            # ── TAB 1: PROFILE & EDIT ──────────────────────────────────────────
            with t_profile:
                # Quick-view row
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**DOJ:** {emp['doj']}")
                c1.markdown(f"**Contact:** {emp['contact'] or '—'}")
                c1.markdown(f"**Gender:** {emp['gender'] or '—'}")
                c2.markdown(f"**Base Salary:** ₹{emp['base_salary']:,.2f}")
                c2.markdown(f"**Bank:** {emp['bank_name'] or '—'}")
                c2.markdown(f"**Account:** {emp['bank_account'] or '—'}")
                c3.markdown(f"**IFSC:** {emp['ifsc_code'] or '—'}")
                c3.markdown(f"**Status:** {emp['status']}")

                st.divider()
                st.markdown("**Edit Details**")
                with st.form(f"edit_{eid}"):
                    ec1, ec2 = st.columns(2)
                    new_name    = ec1.text_input("Full Name", value=emp["name"])
                    new_contact = ec1.text_input("Contact Number", value=emp["contact"] or "")
                    new_gender  = ec1.selectbox(
                        "Gender", ["Male", "Female", "Other"],
                        index=["Male", "Female", "Other"].index(emp["gender"]) if emp["gender"] else 0,
                    )
                    new_doj = ec1.date_input(
                        "Date of Joining",
                        value=doj_date,
                        help="Changing DOJ will affect payroll proration for that month.",
                    )
                    new_status = ec1.selectbox(
                        "Employment Status",
                        ["Active", "Inactive", "Terminated/Left"],
                        index=["Active", "Inactive", "Terminated/Left"].index(emp["status"]),
                    )
                    new_def_shift = ec1.selectbox(
                        "Default Shift",
                        ["Morning", "Evening", "Night"],
                        index=["Morning", "Evening", "Night"].index(emp.get("default_shift", "Morning")),
                    )
                    new_salary = ec2.number_input(
                        "Base Monthly Salary (₹)", value=float(emp["base_salary"]), min_value=0.0
                    )
                    new_bank = ec2.text_input("Bank Name", value=emp["bank_name"] or "")
                    new_acc  = ec2.text_input("Account Number", value=emp["bank_account"] or "")
                    new_ifsc = ec2.text_input("IFSC Code", value=emp["ifsc_code"] or "")

                    if st.form_submit_button("Save Changes", type="primary"):
                        if not new_name.strip() or new_salary <= 0:
                            st.error("Name and salary are required.")
                        else:
                            try:
                                dup = db.find_duplicate_employee(new_contact, new_name, exclude_id=eid)
                                if dup:
                                    if dup["field"] == "contact":
                                        st.error(f"Contact already belongs to '{dup['existing_name']}' (ID {dup['existing_id']}).")
                                    else:
                                        st.error(f"Employee named '{dup['existing_name']}' (ID {dup['existing_id']}) already exists.")
                                else:
                                    db.update_employee(
                                        eid,
                                        name=new_name.strip(), contact=new_contact.strip(), gender=new_gender,
                                        doj=str(new_doj), status=new_status,
                                        base_salary=new_salary, bank_name=new_bank.strip(),
                                        bank_account=new_acc.strip(), ifsc_code=new_ifsc.strip(),
                                        default_shift=new_def_shift,
                                    )
                                    st.success("Profile saved.")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Database error: {str(e)}")

                st.divider()
                st.markdown("**Danger Zone**")
                if st.checkbox(
                    "I confirm — permanently delete this employee and all their records",
                    key=f"confirm_del_{eid}",
                ):
                    if st.button("Delete Employee", key=f"del_emp_{eid}", type="primary"):
                        try:
                            db.delete_employee(eid)
                            st.success(f"'{emp['name']}' deleted.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Database error: {str(e)}")

            # ── TAB 2: ATTENDANCE CALENDAR + AMENDMENT ─────────────────────────
            with t_attendance:
                ck = f"cal_ym_{eid}"
                if ck not in st.session_state:
                    st.session_state[ck] = (date.today().year, date.today().month)
                cal_year, cal_month = st.session_state[ck]

                nav1, nav2, nav3 = st.columns([1, 5, 1])
                if nav1.button("◀", key=f"prev_cal_{eid}"):
                    m, y = cal_month - 1, cal_year
                    if m == 0:
                        m, y = 12, y - 1
                    st.session_state[ck] = (y, m)
                    st.rerun()
                nav2.markdown(
                    f"<p style='text-align:center;font-size:16px;font-weight:700;"
                    f"margin:4px 0'>{calendar.month_name[cal_month]} {cal_year}</p>",
                    unsafe_allow_html=True,
                )
                if nav3.button("▶", key=f"next_cal_{eid}"):
                    m, y = cal_month + 1, cal_year
                    if m == 13:
                        m, y = 1, y + 1
                    st.session_state[ck] = (y, m)
                    st.rerun()

                st.markdown(
                    build_attendance_calendar_html(eid, cal_month, cal_year, doj_date),
                    unsafe_allow_html=True,
                )

                st.divider()
                st.markdown("**Amend Attendance**")

                amend_date = st.date_input(
                    "Select Date",
                    value=date.today(),
                    min_value=doj_date,
                    max_value=date.today(),
                    key=f"amend_d_{eid}",
                )

                existing_rec = db.get_attendance_for_employee_date(eid, amend_date)
                cur_status = existing_rec["att_status"] if existing_rec else "—"
                cur_shift  = existing_rec["shift"] if existing_rec else emp.get("default_shift", "Morning")

                STATUS_OPTS = ["—", "Present", "Half-Day", "Leave"]
                SHIFT_OPTS  = ["Morning", "Evening", "Night"]

                am1, am2 = st.columns(2)
                sel_status = am1.selectbox(
                    "Attendance Status", STATUS_OPTS,
                    index=STATUS_OPTS.index(cur_status) if cur_status in STATUS_OPTS else 0,
                    key=f"amend_s_{eid}",
                )
                sel_shift = am2.selectbox(
                    "Shift", SHIFT_OPTS,
                    index=SHIFT_OPTS.index(cur_shift) if cur_shift in SHIFT_OPTS else 0,
                    key=f"amend_sh_{eid}",
                )

                if existing_rec:
                    st.caption(
                        f"Current record for {amend_date}: **{existing_rec['att_status']}** "
                        f"/ **{existing_rec['shift']}** shift"
                    )
                else:
                    st.caption(f"No record for {amend_date}. Default shift: **{emp.get('default_shift', 'Morning')}**")

                btn1, btn2 = st.columns(2)
                if btn1.button("Save", key=f"amend_save_{eid}", type="primary"):
                    if sel_status == "—":
                        if existing_rec:
                            try:
                                db.delete_attendance(eid, amend_date)
                                st.success(f"Record for {amend_date} cleared.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Database error: {str(e)}")
                        else:
                            st.warning("Select a status before saving.")
                    else:
                        try:
                            db.upsert_attendance(eid, amend_date, sel_status, sel_shift)
                            st.success(f"Attendance saved: {amend_date} → {sel_status} / {sel_shift}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Database error: {str(e)}")

                if btn2.button("Clear Record", key=f"amend_clear_{eid}"):
                    if existing_rec:
                        try:
                            db.delete_attendance(eid, amend_date)
                            st.success(f"Record for {amend_date} cleared.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Database error: {str(e)}")
                    else:
                        st.info("Nothing to clear for this date.")

            # ── TAB 3: PAYOUT HISTORY ──────────────────────────────────────────
            with t_history:
                history = db.get_payroll_history(eid)
                if history:
                    df = pd.DataFrame(history)[
                        ["year", "month", "days_present", "leaves_taken",
                         "leave_pool", "daily_rate", "final_payout", "calculated_at"]
                    ]
                    df.columns = ["Year", "Month", "Days Present", "Leaves",
                                  "Pool", "Daily Rate (₹)", "Payout (₹)", "Calculated At"]
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    total = sum(r["final_payout"] for r in history)
                    st.metric("Lifetime Payout", f"₹{total:,.2f}")
                else:
                    st.info("No payroll records yet. Run the Payroll Calculator to generate.")

    with tab_active:
        emps = db.get_employees("Active")
        if emps:
            for e in emps:
                employee_card(e)
        else:
            st.info("No active employees.")

    with tab_inactive:
        emps = db.get_employees("Inactive")
        if emps:
            for e in emps:
                employee_card(e)
        else:
            st.info("No inactive employees.")

    with tab_terminated:
        emps = db.get_employees("Terminated/Left")
        if emps:
            for e in emps:
                employee_card(e)
        else:
            st.info("No terminated employees.")

    with tab_add:
        st.subheader("Add New Employee")
        with st.form("add_employee"):
            a1, a2 = st.columns(2)
            name    = a1.text_input("Full Name *")
            contact = a1.text_input("Contact Number")
            gender  = a1.selectbox("Gender", ["Male", "Female", "Other"])
            doj     = a1.date_input("Date of Joining *", value=date.today())
            def_shift = a1.selectbox("Default Shift", ["Morning", "Evening", "Night"])
            salary  = a2.number_input("Base Monthly Salary (₹) *", min_value=0.0, step=500.0)
            bank    = a2.text_input("Bank Name")
            acc     = a2.text_input("Bank Account Number")
            ifsc    = a2.text_input("IFSC Code")
            if st.form_submit_button("Add Employee"):
                if not name.strip() or salary <= 0:
                    st.error("Name and salary are required.")
                else:
                    try:
                        dup = db.find_duplicate_employee(contact, name)
                        if dup:
                            if dup["field"] == "contact":
                                st.error(f"Contact number already belongs to '{dup['existing_name']}' (ID {dup['existing_id']}). Cannot add duplicate.")
                            else:
                                st.error(f"An employee named '{dup['existing_name']}' (ID {dup['existing_id']}) already exists. Cannot add duplicate.")
                        else:
                            db.add_employee(
                                name.strip(), contact.strip(), gender, doj, salary,
                                acc.strip(), bank.strip(), ifsc.strip(), def_shift
                            )
                            st.toast(f"✅ Successfully added the employee — {name.strip()}", icon="🎉")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Database error: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — DAILY ATTENDANCE LOGGER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Daily Attendance Logger":
    st.title("Daily Attendance Logger")
    st.caption("Only Active employees are shown. Dates before an employee's DOJ are disabled.")

    log_date = st.date_input("Select Date", value=date.today())
    st.divider()

    active_emps = db.get_employees("Active")
    if not active_emps:
        st.warning("No active employees found. Add employees in the Directory.")
        st.stop()

    existing = db.get_attendance_map(log_date)

    STATUS_OPTIONS = ["—", "Present", "Half-Day", "Leave"]
    SHIFT_OPTIONS  = ["Morning", "Evening", "Night"]

    header = st.columns([3, 2, 2, 1])
    header[0].markdown("**Employee**")
    header[1].markdown("**Status**")
    header[2].markdown("**Shift**")
    header[3].markdown("**Clear**")

    changes = {}

    for emp in active_emps:
        doj = datetime.strptime(emp["doj"], "%Y-%m-%d").date()

        # Overnight / end-of-month night shift: log_date is always the START date,
        # so no special remapping needed here — admin enters the shift-start date.
        before_doj = log_date < doj

        rec = existing.get(emp["id"], {})
        cur_status = rec.get("att_status", "—")
        cur_shift  = rec.get("shift") or emp.get("default_shift", "Morning")

        row = st.columns([3, 2, 2, 1])
        if before_doj:
            row[0].markdown(f"~~{emp['name']}~~  :gray[*(pre-joining)*]")
            row[1].selectbox("", STATUS_OPTIONS, disabled=True, key=f"s_{emp['id']}", label_visibility="collapsed")
            row[2].selectbox("", SHIFT_OPTIONS,  disabled=True, key=f"sh_{emp['id']}", label_visibility="collapsed")
            row[3].markdown("")
        else:
            row[0].markdown(f"**{emp['name']}**")
            status_idx = STATUS_OPTIONS.index(cur_status) if cur_status in STATUS_OPTIONS else 0
            shift_idx  = SHIFT_OPTIONS.index(cur_shift)   if cur_shift  in SHIFT_OPTIONS  else 0

            sel_status = row[1].selectbox("", STATUS_OPTIONS, index=status_idx,
                                          key=f"s_{emp['id']}", label_visibility="collapsed")
            sel_shift  = row[2].selectbox("", SHIFT_OPTIONS,  index=shift_idx,
                                          key=f"sh_{emp['id']}", label_visibility="collapsed")

            if row[3].button("✕", key=f"del_{emp['id']}"):
                try:
                    db.delete_attendance(emp["id"], log_date)
                    st.rerun()
                except Exception as e:
                    st.error(f"Database error: {str(e)}")

            # Collect choices for all employees
            changes[emp["id"]] = (sel_status, sel_shift)

    st.divider()
    if st.button("Save Attendance", type="primary"):
        try:
            for emp_id, (status, shift) in changes.items():
                if status == "—":
                    db.delete_attendance(emp_id, log_date)
                else:
                    db.upsert_attendance(emp_id, log_date, status, shift)
            st.success(f"Attendance saved for {log_date}.")
            st.rerun()
        except Exception as e:
            st.error(f"Database error: {str(e)}")

    # Summary for the selected date
    st.subheader(f"Summary — {log_date}")
    att_rows = db.get_attendance_for_date(log_date)
    if att_rows:
        emp_map = {e["id"]: e["name"] for e in active_emps}
        summary = [
            {"Employee": emp_map.get(r["employee_id"], f"ID {r['employee_id']}"),
             "Status": r["att_status"], "Shift": r["shift"]}
            for r in att_rows
        ]
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
    else:
        st.info("No attendance logged for this date yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — PAYROLL CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Payroll Calculator":
    st.title("Payroll Calculator")

    today = date.today()
    col1, col2 = st.columns(2)
    sel_year  = col1.number_input("Year",  value=today.year,  min_value=2020, max_value=2100, step=1)
    sel_month = col2.number_input("Month", value=today.month, min_value=1,    max_value=12,   step=1)
    sel_year, sel_month = int(sel_year), int(sel_month)

    all_emps = db.get_employees()

    if st.button("Calculate Payroll for All Employees", type="primary"):
        if not all_emps:
            st.warning("No employees found.")
        else:
            rows = []
            db_error = False
            for emp in all_emps:
                doj = datetime.strptime(emp["doj"], "%Y-%m-%d").date()
                # Skip employees who hadn't joined yet this month
                if (doj.year, doj.month) > (sel_year, sel_month):
                    continue
                try:
                    result = pe.calculate_payout(emp["id"], sel_month, sel_year)
                    rows.append(result)
                except Exception as e:
                    st.error(f"Database error while calculating for {emp['name']}: {str(e)}")
                    db_error = True
                    break

            if not db_error:
                if rows:
                    df = pd.DataFrame(rows)[[
                        "name", "days_present", "leaves_taken", "leave_pool",
                        "excess_leaves", "daily_rate", "total_pay_days", "final_payout"
                    ]]
                    df.columns = ["Employee", "Days Present", "Leaves", "Pool",
                                  "Excess Leaves", "Daily Rate (₹)", "Pay Days", "Payout (₹)"]
                    df["Daily Rate (₹)"] = df["Daily Rate (₹)"].map(lambda x: f"₹{x:,.2f}")
                    df["Payout (₹)"]     = df["Payout (₹)"].map(lambda x: f"₹{x:,.2f}")
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    total = sum(r["final_payout"] for r in rows)
                    st.metric("Total Payroll", f"₹{total:,.2f}")
                else:
                    st.info("No employees were employed during this month.")

    st.divider()
    st.subheader("Individual Breakdown")

    emp_options = {e["name"]: e["id"] for e in all_emps}
    if emp_options:
        sel_name = st.selectbox("Select Employee", list(emp_options.keys()))
        sel_id   = emp_options[sel_name]

        if st.button("Run Calculation"):
            result = pe.calculate_payout(sel_id, sel_month, sel_year, persist=False)
            st.markdown(f"### {result['name']}  —  {calendar.month_name[sel_month]} {sel_year}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Days Present",  result["days_present"])
            m2.metric("Leaves Taken",  result["leaves_taken"])
            m3.metric("Leave Pool",    result["leave_pool"])
            m4.metric("Excess Leaves", result["excess_leaves"])
            n1, n2, n3 = st.columns(3)
            n1.metric("Daily Rate",    f"₹{result['daily_rate']:,.2f}")
            n2.metric("Total Pay Days", result["total_pay_days"])
            n3.metric("Final Payout",  f"₹{result['final_payout']:,.2f}")

            st.caption(
                f"Formula: ({result['days_present']} present + {result['leave_pool']} pool "
                f"− {result['excess_leaves']} excess) × ₹{result['daily_rate']:,.2f} "
                f"= ₹{result['final_payout']:,.2f}"
            )

    st.divider()
    st.subheader("Monthly Payroll Summary")
    saved = db.get_payroll_for_month(sel_month, sel_year)
    if saved:
        df2 = pd.DataFrame(saved)[["name", "days_present", "leaves_taken",
                                    "leave_pool", "daily_rate", "final_payout", "calculated_at"]]
        df2.columns = ["Employee", "Days Present", "Leaves", "Pool",
                       "Daily Rate (₹)", "Payout (₹)", "Calculated At"]
        st.dataframe(df2, use_container_width=True, hide_index=True)
    else:
        st.info("No saved payroll for this month. Run the calculator above to generate.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — VALIDATION TESTS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Validation Tests":
    st.title("Payroll Engine Validation")
    st.caption("Runs programmatic assertions against the PRD business rules. No data is written to the database.")

    if st.button("Run Tests", type="primary"):
        results = pe.run_validation_tests()
        all_passed = all(r["passed"] for r in results)

        if all_passed:
            st.success("All tests passed.")
        else:
            st.error("Some tests failed — check details below.")

        for r in results:
            icon = "✅" if r["passed"] else "❌"
            with st.expander(f"{icon}  {r['case']}"):
                st.write(f"**Expected:** ₹{r['expected']:,.2f}")
                st.write(f"**Got:**      ₹{r['got']:,.2f}")
                st.write(f"**Detail:**   {r['detail']}")

    st.divider()
    st.subheader("PRD Business Rule Reference")
    st.markdown("""
**Leave Pool Proration (Mid-Month Joiners)**

| Week of Joining | Standard Pool | Post-Tuesday Cutoff |
|-----------------|--------------|---------------------|
| Week 1 (days 1–7)   | 4 | 3 |
| Week 2 (days 8–14)  | 3 | 2 |
| Week 3 (days 15–21) | 2 | 1 |
| Week 4 (days 22+)   | 1 | 0 |

*Post-Tuesday = joined on Wednesday, Thursday, Friday, Saturday, or Sunday.*

**Payout Formula**

```
daily_rate       = base_salary / calendar_days_in_month
effective_present = days_present + 0.5 × half_days
excess_leaves    = max(0, leaves_taken − leave_pool)
total_pay_days   = effective_present + leave_pool − excess_leaves
final_payout     = total_pay_days × daily_rate
```

**Night Shift Rule:** Always logged against the shift-START date.
**End-of-Month Spillover:** A night shift starting on the last day of a month belongs to that month's payroll.
""")
