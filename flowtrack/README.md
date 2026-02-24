# 🥕 CarrotSummary

**A simple app that tracks what you're working on and helps you stay focused.**

CarrotSummary sits quietly in your menu bar, watches which apps and windows you use, and organizes your work into categories. It includes a built-in Pomodoro timer, a task list, and a dashboard to see how you spend your day.

---

## What It Does

- **Tracks your work automatically** — no manual input needed
- **Pomodoro timer** — 25-minute focus sessions with breaks, managed for you
- **Task list** — auto-populated from your activity, plus manual tasks
- **Daily & weekly summaries** — see where your time goes
- **Dashboard** — a clean web page to view everything at a glance
- **Privacy first** — all data stays on your computer, nothing is sent anywhere

---

## Getting Started (Mac)

### Step 1: Install Python

If you don't have Python installed:

1. Open **Terminal** (press `Cmd + Space`, type "Terminal", press Enter)
2. Copy and paste this command, then press Enter:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

3. Once Homebrew is installed, run:

```
brew install python@3.13
```

### Step 2: Download CarrotSummary

1. Download or clone this project to your computer
2. Open **Terminal**
3. Navigate to the CarrotSummary folder:

```
cd path/to/flowtrack
```

(Tip: you can type `cd ` then drag the folder into Terminal to fill in the path)

### Step 3: Install CarrotSummary

Run these commands one at a time:

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Launch CarrotSummary

```
source venv/bin/activate
python -m flowtrack.main
```

That's it! You'll see a small 🥕 carrot icon appear in your menu bar.

### Step 5: Open the Dashboard

Click the carrot icon in your menu bar and select **Dashboard**. Your browser will open with the CarrotSummary dashboard where you can:

- See the Pomodoro timer counting down
- View your task list
- Check today's activity breakdown
- Change settings

---

## Getting Started (Windows)

### Step 1: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the latest Python 3 installer
3. **Important**: Check the box that says "Add Python to PATH" during installation
4. Click "Install Now"

### Step 2: Download CarrotSummary

1. Download or clone this project to your computer
2. Open **Command Prompt** (press `Win + R`, type `cmd`, press Enter)
3. Navigate to the CarrotSummary folder:

```
cd path\to\flowtrack
```

### Step 3: Install CarrotSummary

Run these commands one at a time:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 4: Launch CarrotSummary

```
venv\Scripts\activate
python -m flowtrack.main
```

You'll see a small icon appear in your system tray (bottom-right of your screen).

### Step 5: Open the Dashboard

Click the icon in your system tray and select **Dashboard**.

---

## Quick Start Script

For convenience, you can create a shortcut to launch CarrotSummary:

**Mac** — save this as `start.sh` in the flowtrack folder:
```bash
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python -m flowtrack.main
```
Then make it runnable: `chmod +x start.sh` and double-click it to launch.

**Windows** — save this as `start.bat` in the flowtrack folder:
```bat
@echo off
cd /d "%~dp0"
call venv\Scripts\activate
python -m flowtrack.main
```
Double-click `start.bat` to launch.

---

## Using CarrotSummary

### Menu Bar / System Tray

Click the carrot icon to see options:
- **Start/Stop Tracking** — pause or resume activity tracking
- **Dashboard** — open the web dashboard in your browser
- **Daily Summary** — see today's work breakdown
- **Weekly Report** — see this week's summary
- **Add Task** — quickly add a Pomodoro task
- **Quit** — close CarrotSummary

### Dashboard (http://localhost:5555)

The dashboard has three tabs:

| Tab | What it shows |
|-----|--------------|
| **Focus** | Pomodoro timer, your two-tier task list (buckets → tasks), set active task for tracking |
| **Activity** | Auto-tracked work organized under your task hierarchy, time per task, calendar view, category breakdown, report generation |
| **Settings** | Edit Pomodoro durations, tracking speed, email settings |

### Focus Tab

The Focus tab is your task management hub:
- Create **buckets** (high-level tasks like "Tickets", "Design Work")
- Add **tasks** under each bucket (like "authentication issue", "mockups")
- Click a task to set it as the **active task** — the Pomodoro timer runs against it and all auto-tracked activity is associated with it
- Drag and drop tasks between buckets to reorganize
- Check off completed tasks
- Auto-generated tasks appear from your detected work contexts

### Activity Tab

The Activity tab shows your auto-tracked work organized under your task hierarchy:
- Each bucket shows its total tracked time
- Under each bucket, tasks show their individual time
- Under each task, you see detailed entries: which app you used, what you did, and how long
- Activities with no active task go under "Unassigned"
- Calendar view lets you browse any day's activity
- Category breakdown shows time by work type with visual bars
- Generate date-range reports

### How Categories Work

CarrotSummary automatically sorts your apps into categories:
- **Document Editing** — Word, Google Docs, Pages
- **Email & Communication** — Outlook, Gmail, Mail
- **Meetings** — Zoom, Teams, Webex
- **Research & Browsing** — Chrome, Firefox, Safari
- **Other** — anything that doesn't match a rule

You can customize these categories in the Settings tab.

### How the Pomodoro Timer Works

1. CarrotSummary detects what you're working on
2. It starts a 25-minute focus session automatically
3. When the session ends, you get a 5-minute break
4. After 4 sessions, you get a 15-minute long break
5. If you switch to a different type of work, CarrotSummary pauses the current session and starts a new one

---

## Troubleshooting

**"Permission denied" on Mac**
CarrotSummary needs permission to see which app is in front. Go to:
System Settings → Privacy & Security → Accessibility → Add Terminal (or your terminal app)

**Dashboard won't open**
Make sure CarrotSummary is running, then manually go to http://localhost:5555 in your browser.

**No activity showing up**
Check that tracking is enabled (click the carrot icon — it should say "Stop Tracking" if it's active).

**Want to reset everything?**
Delete the CarrotSummary data folder:
- Mac: `~/Library/Application Support/CarrotSummary/`
- Windows: `%APPDATA%/CarrotSummary/`

---

## Your Data

All your data is stored locally on your computer in a SQLite database. Nothing is sent to the internet. The data folder is:
- **Mac**: `~/Library/Application Support/CarrotSummary/`
- **Windows**: `%APPDATA%/CarrotSummary/`

---

## For Developers

```bash
# Run tests
cd flowtrack
source venv/bin/activate
python -m pytest

# CLI summaries (no GUI needed)
python -m flowtrack.main --daily
python -m flowtrack.main --weekly

# Rebuild the standalone .app + .dmg
./scripts/rebuild.sh
# Output: dist/CarrotSummary.app (43M) and dist/CarrotSummary.dmg (23M)
```

## Standalone App (No Python Required)

Pre-built standalone apps are available in the `dist/` folder:

- **macOS**: `dist/CarrotSummary.dmg` — mount the disk image and drag to Applications
- **Windows**: `dist/FlowTrack-Windows/` — run `CarrotSummary.exe` directly

To rebuild from source:
```bash
cd flowtrack
./scripts/rebuild.sh    # macOS
scripts\build_windows.bat  # Windows
```

## License

MIT
