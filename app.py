import os, sqlite3, calendar
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "campus_events.db")

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key-before-deployment"
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Event poster upload configuration
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")

    db.executescript("""
    CREATE TABLE IF NOT EXISTS admins (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      category TEXT NOT NULL,
      description TEXT NOT NULL,
      venue TEXT NOT NULL,
      event_date TEXT NOT NULL,
      event_time TEXT NOT NULL,
      capacity INTEGER NOT NULL DEFAULT 100,
      image_emoji TEXT NOT NULL DEFAULT '🎉',
      status TEXT NOT NULL DEFAULT 'Published',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS registrations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id INTEGER NOT NULL,
      student_name TEXT NOT NULL,
      email TEXT NOT NULL,
      student_id TEXT NOT NULL,
      department TEXT NOT NULL,
      phone TEXT NOT NULL,
      registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      status TEXT NOT NULL DEFAULT 'Pending',
      FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
      UNIQUE(event_id, email)
    );
    """)

       # Add new date/time columns without deleting existing data
    columns = {
        row[1]
        for row in db.execute("PRAGMA table_info(events)").fetchall()
    }

    for column in (
        "event_start_date",
        "event_end_date",
        "event_start_time",
        "event_end_time",
    ):
        if column not in columns:
            db.execute(
                f"ALTER TABLE events ADD COLUMN {column} TEXT"
            )

    # Add poster URL support without deleting existing events
    columns = {
        row[1]
        for row in db.execute("PRAGMA table_info(events)").fetchall()
    }

    if "poster_url" not in columns:
        db.execute("ALTER TABLE events ADD COLUMN poster_url TEXT")

    # Preserve existing events using their original dates and times
    db.execute("""
        UPDATE events
        SET event_start_date =
                COALESCE(NULLIF(event_start_date, ''), event_date),
            event_end_date =
                COALESCE(NULLIF(event_end_date, ''), event_date),
            event_start_time =
                COALESCE(NULLIF(event_start_time, ''), event_time),
            event_end_time =
                COALESCE(NULLIF(event_end_time, ''), event_time)
    """)

    count = db.execute(
        "SELECT COUNT(*) FROM admins"
    ).fetchone()[0]

    if not count:
        db.execute(
            "INSERT INTO admins(username, password_hash) VALUES(?, ?)",
            ("admin", generate_password_hash("Campus@123"))
        )

    count = db.execute(
        "SELECT COUNT(*) FROM events"
    ).fetchone()[0]

    if not count:
        samples = [
            ("InnovateX Hackathon", "Technology",
             "A high-energy 12-hour build sprint for bold ideas, prototypes and teamwork.",
             "Innovation Lab, Block B", "2026-11-12", "09:30", 120, "💻", "Published"),
            ("Rhythm & Roots", "Cultural",
             "An evening of music, dance and performances celebrating campus creativity.",
             "Open Air Theatre", "2026-11-18", "17:00", 250, "🎭", "Published"),
            ("Future Leaders Summit", "Seminar",
             "Meet inspiring speakers and explore leadership, careers and emerging industries.",
             "Auditorium", "2026-11-25", "10:00", 180, "🎤", "Published"),
            ("Campus Cup", "Sports",
             "Bring your team spirit to our inter-department sports showdown.",
             "Sports Ground", "2026-12-03", "08:00", 200, "🏆", "Published"),
            ("Design for Good", "Workshop",
             "A hands-on design-thinking workshop focused on meaningful student-led solutions.",
             "Design Studio, Block A", "2026-12-09", "11:00", 60, "🎨", "Published"),
            ("Green Campus Day", "Community",
             "Join a campus clean-up, tree planting and sustainability challenge.",
             "Central Lawn", "2026-12-15", "09:00", 100, "🌱", "Published"),
        ]

        db.executemany("""
            INSERT INTO events(
                title, category, description, venue, event_date,
                event_time, capacity, image_emoji, status
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, samples)

    db.commit()
    db.close()


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Please sign in as an administrator to continue.", "warning")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_globals():
    return {"current_year": datetime.now().year, "admin_logged_in": bool(session.get("admin_id"))}

@app.route("/")
def home():
    db = get_db()
    events = db.execute("""SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registered
                           FROM events e WHERE status='Published' ORDER BY event_date, event_time LIMIT 3""").fetchall()
    total_events = db.execute("SELECT COUNT(*) FROM events WHERE status='Published'").fetchone()[0]
    total_reg = db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    return render_template("index.html", events=events, total_events=total_events, total_reg=total_reg)

@app.route("/events")
def events():
    db = get_db()
    category = request.args.get("category", "").strip()
    search = request.args.get("q", "").strip()
    sql = """SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registered
             FROM events e WHERE e.status='Published'"""
    params = []
    if category:
        sql += " AND e.category=?"; params.append(category)
    if search:
        sql += " AND (e.title LIKE ? OR e.description LIKE ? OR e.venue LIKE ?)"
        params.extend([f"%{search}%"]*3)
    sql += " ORDER BY e.event_date, e.event_time"
    rows = db.execute(sql, params).fetchall()
    categories = [r["category"] for r in db.execute("SELECT DISTINCT category FROM events WHERE status='Published' ORDER BY category")]
    return render_template("events.html", events=rows, categories=categories, selected=category, q=search)

@app.route("/event/<int:event_id>")
def event_detail(event_id):
    event = get_db().execute("""SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registered
                                FROM events e WHERE e.id=? AND e.status='Published'""", (event_id,)).fetchone()
    if not event:
        flash("That event could not be found.", "danger")
        return redirect(url_for("events"))
    return render_template("event_detail.html", event=event)

@app.route("/apply/<int:event_id>", methods=["GET", "POST"])
def apply(event_id):
    db = get_db()
    event = db.execute("""SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registered
                          FROM events e WHERE e.id=? AND e.status='Published'""", (event_id,)).fetchone()
    if not event:
        flash("That event is not available for registration.", "danger")
        return redirect(url_for("events"))
    if request.method == "POST":
        name = request.form.get("student_name","").strip()
        email = request.form.get("email","").strip().lower()
        student_id = request.form.get("student_id","").strip()
        department = request.form.get("department","").strip()
        phone = request.form.get("phone","").strip()
        if not all([name,email,student_id,department,phone]) or "@" not in email:
            flash("Please complete every field with a valid email address.", "danger")
        elif date.fromisoformat(event["event_date"]) < date.today():
            flash("Registration for this past event is closed.", "warning")
        elif event["registered"] >= event["capacity"]:
            flash("Sorry, this event has reached capacity.", "danger")
        else:
            try:
                db.execute("""INSERT INTO registrations(event_id,student_name,email,student_id,department,phone)
                              VALUES(?,?,?,?,?,?)""", (event_id,name,email,student_id,department,phone))
                db.commit()
                return render_template("success.html", event=event, student_name=name)
            except sqlite3.IntegrityError:
                flash("This email is already registered for this event.", "warning")
        return render_template("apply.html", event=event, form=request.form)
    return render_template("apply.html", event=event, form={})

@app.route("/calendar")
def event_calendar():
    today = date.today()

    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))

        if month < 1 or month > 12 or year < 2020 or year > 2100:
            raise ValueError()
    except ValueError:
        year, month = today.year, today.month

    cal = calendar.Calendar(firstweekday=0)
    db = get_db()

    month_start = date(year, month, 1)
    month_end = date(
        year + (month == 12),
        1 if month == 12 else month + 1,
        1
    ) - timedelta(days=1)

    event_rows = db.execute("""
        SELECT
            id,
            title,
            category,
            image_emoji,
            COALESCE(NULLIF(event_start_date, ''), event_date) AS start_date,
            COALESCE(NULLIF(event_end_date, ''), event_date) AS end_date,
            COALESCE(NULLIF(event_start_time, ''), event_time) AS start_time,
            COALESCE(NULLIF(event_end_time, ''), event_time) AS end_time
        FROM events
        WHERE status = 'Published'
          AND COALESCE(NULLIF(event_start_date, ''), event_date) <= ?
          AND COALESCE(NULLIF(event_end_date, ''), event_date) >= ?
    """, (month_end.isoformat(), month_start.isoformat())).fetchall()

    by_date = {}

    for ev in event_rows:
        event = dict(ev)

        start = date.fromisoformat(event["start_date"])
        end = date.fromisoformat(event["end_date"])

        current = max(start, month_start)
        last_day = min(end, month_end)

        while current <= last_day:
            day_key = current.isoformat()
            by_date.setdefault(day_key, []).append(event)
            current += timedelta(days=1)

    prev_month = 12 if month == 1 else month - 1
    prev_year = year - 1 if month == 1 else year

    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if month == 12 else year

    weeks = cal.monthdayscalendar(year, month)

    return render_template(
        "calendar.html",
        year=year,
        month=month,
        month_name=calendar.month_name[month],
        weeks=weeks,
        by_date=by_date,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year,
        today=today.isoformat()
    )

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if session.get("admin_id"): return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        admin = get_db().execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect username or password.", "danger")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
      "events": db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
      "registrations": db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0],
      "students": db.execute("SELECT COUNT(DISTINCT email) FROM registrations").fetchone()[0],
      "upcoming": db.execute("SELECT COUNT(*) FROM events WHERE event_date>=?", (date.today().isoformat(),)).fetchone()[0]
    }
    upcoming = db.execute("""SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registered
                             FROM events e ORDER BY event_date LIMIT 5""").fetchall()
    recent = db.execute("""SELECT r.*, e.title AS event_title FROM registrations r JOIN events e ON e.id=r.event_id
                           ORDER BY r.registered_at DESC LIMIT 6""").fetchall()
    category_counts = db.execute("SELECT category,COUNT(*) AS count FROM events GROUP BY category ORDER BY count DESC").fetchall()
    return render_template("admin_dashboard.html", stats=stats, upcoming=upcoming, recent=recent, category_counts=category_counts)


@app.route("/admin/events", methods=["GET", "POST"])
@admin_required

def admin_events():
    db = get_db()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        venue = request.form.get("venue", "").strip()

        start_date = request.form.get("event_start_date", "").strip()
        end_date = request.form.get("event_end_date", "").strip()
        start_time = request.form.get("event_start_time", "").strip()
        end_time = request.form.get("event_end_time", "").strip()

        try:
            capacity = max(1, int(request.form.get("capacity", "100")))
        except (ValueError, TypeError):
            capacity = 100

        emoji = request.form.get("image_emoji", "🎉").strip()[:8] or "🎉"
        poster = request.files.get("poster")
        poster_url = None

        if not all([
            title, category, description, venue,
            start_date, end_date, start_time, end_time
        ]):
            flash("Please fill in all required event details.", "danger")

        else:
            try:
                start_day = date.fromisoformat(start_date)
                end_day = date.fromisoformat(end_date)

                datetime.strptime(start_time, "%H:%M")
                datetime.strptime(end_time, "%H:%M")

                if end_day < start_day:
                    raise ValueError(
                        "End date must not precede start date."
                    )

                if end_day == start_day and end_time < start_time:
                    raise ValueError(
                        "End time must not precede start time."
                    )

            except ValueError:
                flash(
                    "Enter valid dates and times. "
                    "The end must not be before the start.",
                    "danger"
                )

            else:
                # Upload a poster only when a file is selected.
                if poster and poster.filename:
                    allowed_extensions = {"jpg", "jpeg", "png", "webp"}
                    filename = poster.filename
                    extension = (
                        filename.rsplit(".", 1)[-1].lower()
                        if "." in filename else ""
                    )

                    if extension not in allowed_extensions:
                        flash(
                            "Please upload a JPG, JPEG, PNG, or WebP poster.",
                            "danger"
                        )
                        return redirect(url_for("admin_events"))

                    try:
                        result = cloudinary.uploader.upload(
                            poster,
                            folder="campus_event_hub/posters",
                            resource_type="image",
                            allowed_formats=["jpg", "jpeg", "png", "webp"]
                        )
                        poster_url = result["secure_url"]

                    except Exception:
                        app.logger.exception("Cloudinary poster upload failed")
                        flash(
                            "Poster upload failed. Check your Cloudinary "
                            "environment variables and try again.",
                            "danger"
                        )
                        return redirect(url_for("admin_events"))

                db.execute("""
                    INSERT INTO events (
                        title, category, description, venue,
                        event_date, event_time,
                        capacity, image_emoji,
                        event_start_date, event_end_date,
                        event_start_time, event_end_time,
                        poster_url
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    title, category, description, venue,
                    start_date, start_time,
                    capacity, emoji,
                    start_date, end_date,
                    start_time, end_time,
                    poster_url
                ))

                db.commit()
                flash("Event created successfully.", "success")
                return redirect(url_for("admin_events"))

    rows = db.execute("""
        SELECT e.*,
               (SELECT COUNT(*)
                FROM registrations r
                WHERE r.event_id = e.id) AS registered
        FROM events e
        ORDER BY COALESCE(
            NULLIF(event_start_date, ''), event_date
        ) DESC
    """).fetchall()

    return render_template("admin_events.html", events=rows)


@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
@admin_required
def delete_event(event_id):
    db = get_db()
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    db.commit()
    flash("Event and its registrations were deleted.", "success")
    return redirect(url_for("admin_events"))

@app.route("/admin/events/<int:event_id>/status", methods=["POST"])
@admin_required
def toggle_event(event_id):
    db = get_db()
    row = db.execute("SELECT status FROM events WHERE id=?", (event_id,)).fetchone()
    if row:
        new_status = "Archived" if row["status"] == "Published" else "Published"
        db.execute("UPDATE events SET status=? WHERE id=?", (new_status,event_id))
        db.commit()
        flash(f"Event is now {new_status.lower()}.", "success")
    return redirect(url_for("admin_events"))

@app.route("/admin/registrations")
@admin_required
def admin_registrations():
    status = request.args.get("status","")
    db = get_db()
    sql = """SELECT r.*,e.title AS event_title,e.event_date FROM registrations r
             JOIN events e ON e.id=r.event_id"""
    params = []
    if status in ("Pending","Approved","Waitlisted"):
        sql += " WHERE r.status=?"; params.append(status)
    sql += " ORDER BY r.registered_at DESC"
    rows = db.execute(sql,params).fetchall()
    return render_template("admin_registrations.html", registrations=rows, selected=status)

@app.route("/admin/registrations/<int:registration_id>/status", methods=["POST"])
@admin_required
def update_registration(registration_id):
    status = request.form.get("status","Pending")
    if status not in ("Pending","Approved","Waitlisted"): status = "Pending"
    db = get_db()
    db.execute("UPDATE registrations SET status=? WHERE id=?", (status,registration_id))
    db.commit()
    flash("Registration status updated.", "success")
    return redirect(url_for("admin_registrations"))

@app.route("/admin/registrations/export")
@admin_required
def export_registrations():
    import csv, io
    from flask import make_response
    rows = get_db().execute("""SELECT r.id,e.title,r.student_name,r.email,r.student_id,r.department,r.phone,
                                      r.registered_at,r.status
                               FROM registrations r JOIN events e ON e.id=r.event_id ORDER BY r.registered_at DESC""").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Registration ID","Event","Student Name","Email","Student ID","Department","Phone","Registered At","Status"])
    writer.writerows([tuple(r) for r in rows])
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=campus_registrations.csv"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    return response

# Initialize database when the app starts, including under Gunicorn.
init_db()

if __name__ == "__main__":
    app.run(debug=True)
