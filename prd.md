# Product Requirement Document (PRD)
## Project: Dark Store Attendance & Payroll Tracker (v1.0)

## 1. Overview & Core Objective
An internal management tool designed for a single Admin to track daily employee attendance across multiple shifts in a high-velocity, quick-commerce dark store. The system tracks dynamic workforce history, automates complex monthly salary generation, and self-corrects leaves and mid-month onboarding calculations using strict business rules.

---

## 2. User Roles & System Access
* **Admin User:** The only persona interacting with this system. The Admin has full Read/Write permissions across all modules, including editing sensitive financial profiles and logging daily data.
* **Employees:** Do not have application accounts or access. They exist purely as records managed by the Admin.

---

## 3. Database & Data Models

### 3.1 Employee Profile Schema
The system must preserve every employee record historically. If an employee's status changes, their past attendance records must remain completely intact.

* **Employee ID:** Unique identifier (Auto-generated string/integer).
* **Lifecycle Status:** Enum `[Active, Inactive, Terminated/Left]`.
* **Onboarding Details:** Full Name, Contact Number, Gender, Date of Joining (DOJ).
* **Financial Profiles:** Base Monthly Salary, Bank Account Number, Bank Name, IFSC Code.
* **Historical Ledgers:** Chronological array of monthly attendance matrices and historical monthly payout receipts.

### 3.2 Attendance Record Schema
* **Employee ID:** Foreign key linking to Profile.
* **Date:** Calendar Date `(YYYY-MM-DD)`.
* **Attendance Status (Axis 1):** Enum `[Present, Half-Day, Leave]`.
* **Shift Timing (Axis 2):** Enum `[Morning, Evening, Night]`.

---

## 4. Functional Core Modules

### 4.1 Module 1: Employee Directory
* **View Modes:** An interface allowing the Admin to switch views between Active, Inactive, and Terminated employee listings.
* **Profile Views:** Clicking on an employee displays their full profile details, contact info, bank details, and an aggregate historical overview of past attendance and salary payouts.

### 4.2 Module 2: The Daily Attendance Logger
* **Target Population:** The logger grid must **only show employees currently marked as "Active"**.
* **Logging Grid:** A flat UI interface allowing the Admin to select a date and efficiently toggle **Axis 1 (Status)** and **Axis 2 (Shift)** for each active employee for that day.
* **The Overnight Shift Rule:** If an employee is logged for a `Night Shift` starting at 10:00 PM on a Monday and finishing at 7:00 AM on a Tuesday, this shift counts entirely as attendance for **Monday**.
* **The End-of-Month Spillover Rule:** A Night Shift starting on the last calendar day of a month (e.g., June 30th) belongs entirely to that month's payroll calculations, even if the shift concludes on the morning of the next month (e.g., July 1st).

### 4.3 Module 3: Dynamic Onboarding Restrictions
* **Historical Day-Locking:** For any employee who joined mid-month, any date in the logger interface prior to their official `Date of Joining (DOJ)` must be visualised as greyed out, disabled, and invalid for logging.
* **First-Mark Baseline:** The system evaluates all payroll constraints from the absolute first valid day an attendance mark is entered for that specific employee.

---

## 5. Payroll & Salary Calculation Engine

### 5.1 Math Formulas & Rules
At the end of each month, the engine runs a calculation based on a fixed **4 Paid Leaves** allotment model.

1. **Daily Rate Calculation:**
   $$Daily\ Rate = \frac{Base\ Monthly\ Salary}{Total\ Calendar\ Days\ in\ Current\ Month\ (28, 29, 30, 31)}$$

2. **The 4 Paid Leaves Allotment & Overtime Multiplier:**
   * Every employee receives a default credit of 4 paid leaves a month.
   * **The Dynamic Bonus Factor:** If an employee takes **0 leaves** in a full month, they are compensated for their work plus their unspent leave pool as a bonus. They effectively get paid for:
     $$Total\ Pay\ Days = Days\ Present + 4$$
   * A `Half-Day` increment adds exactly $0.5$ to the overall `Days Present` count.

3. **The Simple Leave/Deduction Check:**
   * There is no functional concept of tracking "Week-offs" versus "Personal Leaves" in the code logic. There is only a `Leave` mark.
   * If an employee's total accumulated `Leave` marks for the month is $\le 4$, they face **0 deductions** (the leaves are covered by the allocation).
   * Any accumulated `Leave` mark **greater than 4** converts directly to an `Unpaid Leave`, resulting in a direct subtraction of $1 \times Daily\ Rate$ per excess leave from their maximum possible salary output.

### 5.2 Mid-Month Joining & Prorating Logic
If an employee joins the store mid-month, their **4 Paid Leaves** pool must be automatically prorated using a strict standard calendar week breakdown:

* **Proration Allocations:**
    * Joined during Week 1: Holds 4 Paid Leaves.
    * Joined during Week 2: Holds 3 Paid Leaves.
    * Joined during Week 3: Holds 2 Paid Leaves.
    * Joined during Week 4: Holds 1 Paid Leave.
* **The Post-Tuesday Cutoff Rule:** Within the specific calendar week that the employee joins, if their onboarding day falls **post-Tuesday** (Wednesday, Thursday, Friday, Saturday, or Sunday), they completely forfeit the paid leave entitlement for that specific week. Their total starting pool decreases by an additional $-1$ day.
* **Mid-Month Onboarding Formula:**
    $$\text{Final Payout} = \left(\text{Actual Days Present} + \text{Remaining Allowed Paid Leaves Held}\right) \times \text{Daily Rate}$$
    *(Note: All historical calendar dates prior to their DOJ are completely excluded from calculations).*

---

## 6. Technical Execution Instructions for Claude Code

> ### 🤖 [INSTRUCTION FOR CLAUDE CODE]
> You are tasked with implementing the Attendance and Payroll Tracker system based entirely on the specifications detailed in this PRD. Follow these steps strictly:
>
> 1. **Tech Stack Selection:** Choose a lightweight, robust stack suitable for an internal admin desktop or local web tool (e.g., Python with Streamlit/SQLite, or Node.js with React/Express/SQLite). 
> 2. **Database Execution:** Create an SQLite database structure mapping out the schemas in Section 3. Ensure cascading rules protect history when an employee profile is moved to `Inactive` or `Terminated`.
> 3. **Implement Core Rules in Code:**
>    * Write a backend utility module `payroll_engine` that executes the mathematical formulas in Section 5 exactly. 
>    * Ensure the `Daily Rate` uses dynamic calendar day denominators.
>    * Build a parsing rule for the **Post-Tuesday Cutoff Rule** that inspects the Day-of-Week index of the employee's `DOJ` string before setting their monthly leave allocation limit.
>    * Ensure night shift logs map safely to the starting date timestamp.
> 4. **UI/UX Scaffolding:** Build a clean, highly functional admin panel. Ensure that if an employee is not `Active`, they do not render on the daily logging form. Ensure past invalid dates for mid-month joiners are greyed out and unclickable.
> 5. **Validation Testing:** Create mock employees (one standard full-month employee with 0 leaves, one with 5 leaves, and one who joins mid-month on a Thursday) to programmatically assert that the calculation engine produces 100% accurate payouts matching the examples specified in the rules.
>
> Proceed to write the application files cleanly, modularly, and completely. Do not leave placeholder code or `TODO` blocks.