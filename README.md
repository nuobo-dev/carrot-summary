# 🥕 Carrot Summary (FlowTrack)

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

### 1. Install Python (if you don't have it)

Open **Terminal** (press `Cmd + Space`, type "Terminal", press Enter) and run:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then:

```
brew install python@3.13
```

### 2. Install & Launch

```
cd flowtrack
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m flowtrack.main
```

A 🥕 carrot icon will appear in your menu bar. Click it and select **Dashboard** to open the web UI.

### Quick Launch (after first setup)

```
cd flowtrack
source venv/bin/activate
python -m flowtrack.main
```

Or just double-click `flowtrack/start.sh`.

---

## Setup (Windows)

### 1. Install Python

Go to [python.org/downloads](https://www.python.org/downloads/), download Python 3, and install it. **Check "Add Python to PATH"** during installation.

### 2. Install & Launch

Open **Command Prompt** and run:

```
cd flowtrack
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m flowtrack.main
```

An icon will appear in your system tray. Click it and select **Dashboard**.

Or just double-click `flowtrack\start.bat`.

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
- **Quit** — close FlowTrack

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Permission denied" on Mac | System Settings → Privacy & Security → Accessibility → add your Terminal app |
| Dashboard won't open | Make sure FlowTrack is running, then go to http://localhost:5555 |
| No activity showing | Click the carrot icon — make sure it says "Stop Tracking" (meaning it's active) |
| Reset everything | Delete `~/Library/Application Support/FlowTrack/` (Mac) or `%APPDATA%/FlowTrack/` (Windows) |

---

## Your Data

Everything is stored locally in a SQLite database on your machine. Nothing leaves your computer.

- **Mac**: `~/Library/Application Support/FlowTrack/`
- **Windows**: `%APPDATA%/FlowTrack/`
