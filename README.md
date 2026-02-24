# 🥕 Carrot Summary (CarrotSummary)

A simple app that tracks what you're working on and helps you stay focused. It sits quietly in your menu bar, watches which apps and windows you use, and organizes your work into categories — with a built-in Pomodoro timer, task list, and dashboard.

---

## What It Does

- **Tracks your work automatically** — no manual input needed
- **Pomodoro timer** — 25-minute focus sessions with breaks, managed for you
- **Task list** — auto-populated from your activity, plus manual tasks
- **Daily & weekly summaries** — see where your time goes
- **Web dashboard** — a clean page to view everything at http://localhost:5555
- **Privacy first** — all data stays on your computer, nothing is sent anywhere

---

## Setup (Mac)

### Option A: One-Click Install (Recommended)

1. Download `CarrotSummary.dmg` from the `flowtrack/dist/` folder
2. Double-click the `.dmg` file to open it
3. Drag **CarrotSummary** to your **Applications** folder
4. Open **CarrotSummary** from Applications

That's it. A 🥕 carrot icon will appear in your menu bar. Click it and select **Dashboard**.

> **First launch note**: macOS may say "CarrotSummary can't be opened because it is from an unidentified developer." If this happens, go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**.

### Option B: Run from Source (for developers)

```
cd flowtrack
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m flowtrack.main
```

---

## Setup (Windows)

### Option A: One-Click Install (Recommended)

1. Download the `CarrotSummary.zip` from the `flowtrack/dist/` folder
2. Extract the zip file
3. Double-click **CarrotSummary.exe** inside the extracted folder

An icon will appear in your system tray. Click it and select **Dashboard**.

### Option B: Run from Source (for developers)

1. Install Python from [python.org/downloads](https://www.python.org/downloads/) — **check "Add Python to PATH"**
2. Open Command Prompt and run:

```
cd flowtrack
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m flowtrack.main
```

---

## Using the Dashboard

Open http://localhost:5555 (or click **Dashboard** from the tray menu). Four tabs:

| Tab | What it shows |
|-----|--------------|
| **Timer** | Live Pomodoro countdown, current task, session dots |
| **Tasks** | To-do list (auto-generated from activity + manual) |
| **Activity** | Today's time breakdown by category |
| **Settings** | Pomodoro durations, poll interval, email config |

---

## Menu Bar Options

- **Start/Stop Tracking** — pause or resume
- **Dashboard** — open the web UI
- **Daily Summary** — today's breakdown
- **Weekly Report** — this week's summary
- **Add Task** — start a manual Pomodoro task
- **Quit** — close CarrotSummary

---

## Email Reports (Optional)

CarrotSummary can email your weekly summary report to you automatically. This is completely optional — if you skip this, reports are still viewable in the dashboard.

To set it up, go to the **Settings** tab in the dashboard and fill in the Email / Report section.

### What Each Field Means

| Field | What it is | Example |
|-------|-----------|---------|
| **SMTP Server** | Your email provider's outgoing mail server address | `smtp.gmail.com` |
| **Port** | The port number for the mail server (usually 587) | `587` |
| **Username** | Your email address | `[email]` |
| **Password** | Your email password or app-specific password | (see below) |
| **Recipient** | The email address to send reports to (can be the same as username) | `[email]` |

### Setup for Gmail

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. You may need to enable 2-Step Verification first
3. Create an app password — select "Mail" and "Mac" (or "Other")
4. Google will give you a 16-character password — copy it
5. In CarrotSummary Settings, enter:
   - SMTP Server: `smtp.gmail.com`
   - Port: `587`
   - Username: your full Gmail address
   - Password: the 16-character app password from step 4
   - Recipient: your email address

### Setup for Outlook / Hotmail

1. In CarrotSummary Settings, enter:
   - SMTP Server: `smtp-mail.outlook.com`
   - Port: `587`
   - Username: your full Outlook email address
   - Password: your Outlook password
   - Recipient: your email address

### Setup for Yahoo Mail

1. Go to Yahoo Account Security and generate an app password
2. In CarrotSummary Settings, enter:
   - SMTP Server: `smtp.mail.yahoo.com`
   - Port: `587`
   - Username: your full Yahoo email address
   - Password: the app password from step 1
   - Recipient: your email address

### Setup for iCloud Mail

1. Go to [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → App-Specific Passwords
2. Generate a new app password
3. In CarrotSummary Settings, enter:
   - SMTP Server: `smtp.mail.me.com`
   - Port: `587`
   - Username: your full iCloud email address
   - Password: the app-specific password from step 2
   - Recipient: your email address

### Why "App Password" Instead of My Regular Password?

Most email providers now require two-factor authentication. When that's enabled, you can't use your regular password for apps like CarrotSummary. Instead, you generate a special "app password" that works only for this purpose. It's more secure — you can revoke it anytime without changing your main password.

### Don't Want Email Reports?

Just leave the email fields blank. Your reports will still be available in the dashboard under **Activity** and **Weekly Report** in the tray menu.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Permission denied" on Mac | System Settings → Privacy & Security → Accessibility → add your Terminal app |
| Dashboard won't open | Make sure CarrotSummary is running, then go to http://localhost:5555 |
| No activity showing | Click the carrot icon — make sure it says "Stop Tracking" (meaning it's active) |
| Reset everything | Delete `~/Library/Application Support/CarrotSummary/` (Mac) or `%APPDATA%/CarrotSummary/` (Windows) |

---

## Your Data

Everything is stored locally in a SQLite database on your machine. Nothing leaves your computer.

- **Mac**: `~/Library/Application Support/CarrotSummary/`
- **Windows**: `%APPDATA%/CarrotSummary/`

---

## Rebuilding the App After Changes

If you make code changes and want to update the standalone `.app` and `.dmg`:

```
cd flowtrack
./scripts/rebuild.sh
```

This script will:
1. Install/update dependencies
2. Run all tests (stops if any fail)
3. Build `dist/CarrotSummary.app` via PyInstaller
4. Package it into `dist/CarrotSummary.dmg`

After it finishes, you can test with `open dist/CarrotSummary.app` or distribute the `.dmg`.
