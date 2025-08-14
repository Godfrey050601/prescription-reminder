from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

DB_PATH = "reminders.db"

app = Flask(__name__)
scheduler = BackgroundScheduler(timezone="Africa/Johannesburg")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            med_name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            schedule_time TEXT NOT NULL,  -- ISO string
            repeat_minutes INTEGER NULL,  -- optional repeat interval
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_all_reminders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, med_name, dosage, schedule_time, repeat_minutes, created_at FROM reminders ORDER BY datetime(schedule_time) ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_reminder(reminder_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, med_name, dosage, schedule_time, repeat_minutes, created_at FROM reminders WHERE id = ?", (reminder_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_reminder(med_name, dosage, schedule_dt: datetime, repeat_minutes: int | None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO reminders (med_name, dosage, schedule_time, repeat_minutes, created_at) VALUES (?, ?, ?, ?, ?)",
        (med_name, dosage, schedule_dt.isoformat(timespec="minutes"), repeat_minutes, datetime.now().isoformat(timespec="minutes"))
    )
    conn.commit()
    rid = c.lastrowid
    conn.close()
    return rid

def delete_reminder_db(reminder_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def schedule_job(reminder_id, when: datetime):
    """Schedule a one-off job for this reminder occurrence."""
    # Use a unique job id per occurrence (id + timestamp)
    job_id = f"reminder_{reminder_id}_{int(when.timestamp())}"
    if scheduler.get_job(job_id):
        return
    scheduler.add_job(
        func=fire_reminder,
        trigger=DateTrigger(run_date=when),
        args=[reminder_id],
        id=job_id,
        replace_existing=True
    )

def fire_reminder(reminder_id):
    """Called by scheduler when reminder is due. Prints to console and reschedules if repeating."""
    row = get_reminder(reminder_id)
    if not row:
        return
    _id, med_name, dosage, schedule_time, repeat_minutes, _created = row
    print(f"🔔 Reminder: Take {med_name} — {dosage}  (due at {schedule_time})")

    # If repeating, schedule next occurrence
    if repeat_minutes and repeat_minutes > 0:
        next_time = datetime.fromisoformat(schedule_time) + timedelta(minutes=repeat_minutes)
        # Update the stored next schedule_time
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE reminders SET schedule_time = ? WHERE id = ?", (next_time.isoformat(timespec="minutes"), reminder_id))
        conn.commit()
        conn.close()
        schedule_job(reminder_id, next_time)

def bootstrap_jobs():
    """Load all reminders from DB and schedule the next occurrence (if in the future)."""
    rows = get_all_reminders()
    now = datetime.now()
    for _id, _med, _dosage, schedule_time, _repeat, _created in rows:
        try:
            when = datetime.fromisoformat(schedule_time)
        except ValueError:
            continue
        if when > now:
            schedule_job(_id, when)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        med_name = request.form.get("med_name", "").strip()
        dosage = request.form.get("dosage", "").strip()
        date = request.form.get("date", "")
        time = request.form.get("time", "")
        repeat = request.form.get("repeat_minutes", "").strip()

        if not med_name or not dosage or not date or not time:
            return "Missing fields", 400

        try:
            schedule_dt = datetime.fromisoformat(f"{date}T{time}")
        except ValueError:
            return "Invalid date/time", 400

        repeat_minutes = int(repeat) if repeat.isdigit() and int(repeat) > 0 else None

        rid = save_reminder(med_name, dosage, schedule_dt, repeat_minutes)
        # schedule first occurrence
        if schedule_dt > datetime.now():
            schedule_job(rid, schedule_dt)

        return redirect(url_for("index"))

    # GET: show form + table
    rows = get_all_reminders()
    return render_template("index.html", reminders=rows)

@app.route("/delete/<int:reminder_id>", methods=["POST"])
def delete_reminder(reminder_id):
    # remove any scheduled jobs for this reminder
    # (jobs are one-off with id that includes timestamp; we can't easily enumerate all)
    # We simply delete from DB; future jobs won’t be scheduled again.
    delete_reminder_db(reminder_id)
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    if not scheduler.running:
        scheduler.start()
    bootstrap_jobs()
    print("✅ Prescription Reminder running. Add a reminder and watch the console for 🔔 messages at the scheduled time.")
    app.run(debug=True)
