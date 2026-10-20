# Campus Event Hub — College Event Management System

A full-stack college event portal built with **Python Flask + SQLite + HTML/CSS/JavaScript**.

## Features
- Aesthetic responsive homepage and student-facing event catalogue.
- Search and category filters.
- Event detail pages and direct student applications.
- SQLite database for events, administrators and registrations.
- Monthly event calendar.
- Admin login and dashboard with event/registration statistics.
- Create, archive/publish and delete events.
- View registrations, update status (Pending / Approved / Waitlisted), export CSV.
- Duplicate registration protection per event/email.
- Demo events are seeded automatically on first run.

## Run in VS Code (Windows)
1. Install Python 3.10+ from python.org and VS Code.
2. Extract the ZIP and open the `campus_event_hub` folder in VS Code.
3. Open Terminal → New Terminal.
4. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again.
5. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
6. Start the website:
   ```powershell
   python app.py
   ```
7. Open `http://127.0.0.1:5000` in your browser.

The SQLite file `campus_events.db` is created automatically at first run.

## Demo administrator login
- **Username:** `admin`
- **Password:** `Campus@123`
- Admin portal: `http://127.0.0.1:5000/admin/login`

Change the demo password and `SECRET_KEY` before hosting this online. This is a college-project starter; before public production deployment, add CSRF protection, password-change/reset flows, rate limiting, HTTPS, and environment-based secrets. Debug mode is enabled for local development only.

## Project structure
```text
campus_event_hub/
├── app.py
├── requirements.txt
├── README.md
├── campus_events.db       # generated when you run app.py
├── static/
│   ├── css/style.css
│   └── js/main.js
└── templates/
    ├── base.html
    ├── index.html
    ├── events.html
    ├── event_detail.html
    ├── apply.html
    ├── success.html
    ├── calendar.html
    ├── admin_login.html
    ├── admin_dashboard.html
    ├── admin_events.html
    └── admin_registrations.html
```
