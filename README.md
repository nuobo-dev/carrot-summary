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

### Option A: One-Click Install (Recommended)

1. Download `FlowTrack.dmg` from the `flowtrack/dist/` folder
2. Double-click the `.dmg` file to open it
3. Drag **FlowTrack** to your **Applications** folder
4. Open **FlowTrack** from Applications

That's it. A 🥕 carrot icon will appear in your menu bar. Click it and select **Dashboard**.

> **First launch note**: macOS may say "FlowTrack can't be opened because it is from an unidentified developer." If this happens, go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**.

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

1. Download the `FlowTrack.zip` from the `flowtrack/dist/` folder
2. Extract the zip file
3. Double-click **FlowTrack.exe** inside the extracted folder

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
