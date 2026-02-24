# Implementation Plan: FlowTrack

## Overview

Build FlowTrack as a cross-platform Python desktop app with system tray UI, automatic activity tracking, Pomodoro management, and weekly report export. The app features a two-tier user-defined task list (Focus tab) and an auto-tracked activity view organized under those tasks (Activity tab). Implementation proceeds bottom-up: data models and persistence first, then core logic, then reporting, then UI and packaging.

## Tasks

- [x] 1. Set up project structure and dependencies
  - Create `flowtrack/` package directory structure with `__init__.py` files for subpackages: `core/`, `platform/`, `persistence/`, `reporting/`, `ui/`
  - Create `requirements.txt` with dependencies: `pystray`, `Pillow`, `python-docx`, `hypothesis`
  - Create `setup.py` or `pyproject.toml` for package metadata
  - Create `assets/` directory with placeholder icon files (icon.ico, icon.icns, icon.png)
  - _Requirements: 11.1, 11.6_

- [x] 2. Implement data models and persistence
  - [x] 2.1 Create core data models
    - Implement `WindowInfo`, `ClassificationRule`, `ContextRule`, `ContextResult`, `SessionStatus`, `PomodoroSession`, `ActivityRecord` dataclasses in `flowtrack/core/models.py`
    - Implement `CategorySummary`, `DailySummary`, `WeeklySummary` dataclasses in `flowtrack/core/models.py`
    - Implement `SmtpConfig` dataclass in `flowtrack/core/models.py`
    - _Requirements: 1.2, 2.2, 5.2, 5.3, 9.1_

  - [x] 2.2 Implement ActivityStore with SQLite
    - Create `flowtrack/persistence/store.py` with `ActivityStore` class
    - Implement `init_db()` to create tables (activity_logs, pomodoro_sessions) with indexes
    - Implement `save_activity()`, `get_activity_by_id()`, `get_activities(start, end)`
    - Implement `save_session()`, `get_session_by_id()`, `get_sessions(start, end)`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 2.3 Write property tests for ActivityStore round-trips
    - **Property 10: Activity record database round-trip**
    - **Validates: Requirements 5.4**
    - **Property 11: Pomodoro session database round-trip**
    - **Validates: Requirements 5.3**

  - [x] 2.4 Implement configuration loader
    - Create `flowtrack/core/config.py` with `load_config()` and `save_config()` functions
    - Handle default config creation on first launch
    - Resolve platform-appropriate data directories (macOS: ~/Library/Application Support/FlowTrack, Windows: %APPDATA%/FlowTrack)
    - _Requirements: 11.4, 11.5, 2.4_

- [x] 3. Implement classification and context analysis
  - [x] 3.1 Implement Classifier
    - Create `flowtrack/core/classifier.py` with `Classifier` class
    - Implement `classify(app_name, window_title) -> str` with regex-based rule matching
    - Implement `load_rules()` and `save_rules()` for JSON serialization
    - Return "Other" when no rule matches
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [ ]* 3.2 Write property tests for Classifier
    - **Property 1: Classifier always returns exactly one valid category**
    - **Validates: Requirements 2.1, 2.2, 2.3**
    - **Property 2: Classification rules JSON round-trip**
    - **Validates: Requirements 2.5**

  - [x] 3.3 Implement Context Analyzer
    - Create `flowtrack/core/context_analyzer.py` with `ContextAnalyzer` class
    - Implement `analyze(app_name, window_title, category) -> ContextResult`
    - Pattern matching with named regex groups for extracting document names
    - Fall back to Work_Category when no context rule matches
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 3.4 Write property tests for Context Analyzer
    - **Property 3: Context Analyzer rule matching**
    - **Validates: Requirements 9.2, 9.3, 9.4, 9.5, 9.6**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Pomodoro Manager
  - [x] 5.1 Implement PomodoroManager core logic
    - Create `flowtrack/core/pomodoro.py` with `PomodoroManager` class
    - Implement `on_activity(category, sub_category, timestamp)` with debounce logic
    - Implement `tick(now)` for timer progression, work completion, and break transitions
    - Implement `get_break_duration(completed_count)` for short/long break selection
    - Implement session pause/resume logic keyed by category
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4_

  - [ ]* 5.2 Write property tests for Pomodoro intervals and transitions
    - **Property 4: Break duration follows Pomodoro intervals**
    - **Validates: Requirements 3.1**
    - **Property 5: Work completion triggers break**
    - **Validates: Requirements 3.2**
    - **Property 6: Break completion signals readiness**
    - **Validates: Requirements 3.3**

  - [ ]* 5.3 Write property tests for context switch debounce
    - **Property 7: Debounce prevents premature context switches**
    - **Validates: Requirements 4.1, 4.4**
    - **Property 8: Context switch after debounce threshold**
    - **Validates: Requirements 4.2, 4.3**
    - **Property 9: Session resume preserves state**
    - **Validates: Requirements 4.3**

- [x] 6. Implement platform window providers
  - [x] 6.1 Implement WindowProvider interface and factory
    - Create `flowtrack/platform/base.py` with abstract `WindowProvider` class
    - Create `flowtrack/platform/factory.py` with `create_window_provider()` that detects OS
    - _Requirements: 1.5_

  - [x] 6.2 Implement MacOS window provider
    - Create `flowtrack/platform/macos.py` with `MacOSWindowProvider`
    - Use `subprocess` + `osascript` to get frontmost app name and window title
    - Implement idle detection via `ioreg` idle time query
    - _Requirements: 1.1, 1.4_

  - [x] 6.3 Implement Windows window provider
    - Create `flowtrack/platform/windows.py` with `WindowsWindowProvider`
    - Use `ctypes` with `user32.dll` for `GetForegroundWindow`, `GetWindowText`
    - Implement idle detection via `GetLastInputInfo`
    - _Requirements: 1.1, 1.4_

- [x] 7. Implement Tracker orchestrator
  - [x] 7.1 Implement Tracker
    - Create `flowtrack/core/tracker.py` with `Tracker` class
    - Implement `poll_once(now)`: get window → classify → analyze context → update pomodoro → persist
    - Implement `run()` main loop with configurable poll interval and idle skip
    - Handle window API errors gracefully (log and continue)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 7.2 Write property test for Tracker record completeness
    - **Property 18: Tracker produces complete activity records**
    - **Validates: Requirements 1.2**

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement reporting layer
  - [x] 9.1 Implement Summary Generator
    - Create `flowtrack/reporting/summary.py` with `SummaryGenerator` class
    - Implement `daily_summary(target_date)`: query store, group by category, sort by time descending
    - Implement `weekly_summary(start_date)`: produce 7-day breakdown with aggregated totals
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 9.2 Write property tests for Summary Generator
    - **Property 12: Daily summary filters by date**
    - **Validates: Requirements 6.1**
    - **Property 13: Summary grouping preserves total time**
    - **Validates: Requirements 6.2, 6.3**
    - **Property 14: Summary categories sorted by time descending**
    - **Validates: Requirements 6.4**
    - **Property 15: Weekly summary covers exactly 7 days**
    - **Validates: Requirements 7.1**
    - **Property 16: Weekly totals equal sum of daily breakdowns**
    - **Validates: Requirements 7.2, 7.3, 7.4**

  - [x] 9.3 Implement Text Formatter
    - Create `flowtrack/reporting/formatter.py` with `TextFormatter` class
    - Implement `format_duration(timedelta) -> str` and `parse_duration(str) -> timedelta`
    - Implement `format_daily(DailySummary) -> str` and `format_weekly(WeeklySummary) -> str` with aligned columns
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 9.4 Write property test for duration round-trip
    - **Property 17: Duration format/parse round-trip**
    - **Validates: Requirements 8.3**

  - [x] 9.5 Implement Report Exporter
    - Create `flowtrack/reporting/exporter.py` with `ReportExporter` class
    - Use `python-docx` to generate .docx with title page, category tables, day-by-day breakdown
    - _Requirements: 10.1, 10.2, 10.6_

  - [x] 9.6 Implement Email Sender
    - Create `flowtrack/reporting/email_sender.py` with `EmailSender` class
    - Use `smtplib` and `email` modules for SMTP delivery with .docx attachment
    - Handle failures: log error, retain document locally
    - _Requirements: 10.3, 10.4, 10.5_

- [x] 10. Implement UI layer (existing)
  - [x] 10.1 Implement Settings Window
    - Create `flowtrack/ui/settings.py` with `SettingsWindow` class using tkinter + ttk
    - Build Email tab (SMTP config + test connection button)
    - Build Categories tab (add/edit/remove Work_Categories and keyword rules)
    - Build Context Rules tab (add/edit/remove Sub_Category patterns)
    - Build Pomodoro tab (durations, debounce)
    - Apply minimalistic ttk.Style theme (muted colors, flat design, system fonts)
    - Pre-populate fields from current config, save and apply on confirm
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 10.2 Implement System Tray Application
    - Create `flowtrack/ui/app.py` with `FlowTrackApp` class
    - Use pystray for system tray icon with menu: Start/Stop, Daily Summary, Weekly Report, Settings, Quit
    - Start Tracker in background thread on launch
    - Wire summary display as toast notifications or simple popup windows
    - Wire settings to open SettingsWindow
    - _Requirements: 11.2, 11.3_

  - [x] 10.3 Create main entry point
    - Create `flowtrack/main.py` as the application entry point
    - Initialize config (create defaults if first launch), create all components, start FlowTrackApp
    - Add CLI fallback for `--daily` and `--weekly` summary commands (no GUI needed)
    - _Requirements: 11.4, 11.5_

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Packaging and distribution
  - [x] 12.1 Create PyInstaller spec files
    - Create `flowtrack.spec` for PyInstaller with platform-specific settings
    - Configure `--windowed` mode, icon paths, and hidden imports (pystray, tkinter)
    - Include `assets/` directory in the bundle
    - _Requirements: 11.1, 11.6_

  - [x] 12.2 Create build scripts
    - Create `scripts/build_macos.sh` for macOS .app bundle + .dmg creation
    - Create `scripts/build_windows.bat` for Windows .exe + .zip creation
    - _Requirements: 11.6_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

---

## NEW: Focus Tab & Activity Tab Feature Tasks

- [x] 14. Add `active_task_id` and `activity_summary` to data models and persistence
  - [x] 14.1 Update `ActivityRecord` model
    - Add `active_task_id: Optional[int]` field to `ActivityRecord` in `flowtrack/core/models.py`
    - Add `activity_summary: str` field to `ActivityRecord` (default empty string)
    - _Requirements: 1.2, 5.2, 14.2_

  - [x] 14.2 Update `PomodoroSession` model
    - Add `active_task_id: Optional[int]` field to `PomodoroSession` in `flowtrack/core/models.py`
    - _Requirements: 3.5_

  - [x] 14.3 Update `ContextResult` model
    - Add `activity_summary: str` field to `ContextResult` in `flowtrack/core/models.py`
    - _Requirements: 14.2, 14.3_

  - [x] 14.4 Update ActivityStore schema and queries
    - Add `focus_tasks` table to `init_db()` with columns: id, title, category, parent_id, done, auto_generated, created_at, sort_order
    - Add `active_task_id` and `activity_summary` columns to `activity_logs` table
    - Add `active_task_id` column to `pomodoro_sessions` table
    - Add index on `activity_logs.active_task_id`
    - Update `save_activity()` and `get_activities()` to handle new fields
    - Update `save_session()` and `get_sessions()` to handle `active_task_id`
    - _Requirements: 5.2, 13.9, 14.1_

  - [x] 14.5 Add focus task CRUD methods to ActivityStore
    - Implement `get_todos(include_done)` — return all focus tasks with parent/child hierarchy
    - Implement `add_todo(title, category, parent_id)` — create High_Level or Low_Level task
    - Implement `toggle_todo(task_id)` — toggle done status
    - Implement `delete_todo(task_id)` — delete task and children
    - Implement `move_todo(task_id, new_parent_id)` — move Low_Level_Task between High_Level_Tasks
    - Implement `merge_buckets(source_id, target_id)` — merge two High_Level_Tasks
    - Implement `clear_all_todos()` and `clear_auto_todos()`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.9_

  - [x] 14.6 Add activity-by-task query methods to ActivityStore
    - Implement `get_activities_by_task(task_id, start, end)` — activities for a specific Low_Level_Task
    - Implement `get_activity_summary_by_task(task_id, start, end)` — aggregated entries grouped by app/context with time totals and summaries
    - _Requirements: 14.1, 14.2, 14.5_

- [x] 15. Update Context Analyzer to generate activity summaries
  - [x] 15.1 Add `activity_summary` generation to `ContextAnalyzer.analyze()`
    - Generate a human-readable summary of what the user is doing based on window title and app name
    - Examples: "researched authentication issue, documented findings", "edited design spec v2", "reviewed pull request #42"
    - Use smart title parsing patterns to produce concise summaries
    - Fall back to "{app_name}: {cleaned_title}" when no smart pattern matches
    - _Requirements: 14.2, 14.3_

- [x] 16. Update Tracker to tag activities with Current_Active_Task
  - [x] 16.1 Add `current_active_task_id` to Tracker
    - Add `current_active_task_id: Optional[int]` attribute to `Tracker`
    - In `poll_once()`, set `active_task_id` on each `ActivityRecord` from `current_active_task_id`
    - In `poll_once()`, set `activity_summary` on each `ActivityRecord` from `ContextResult.activity_summary`
    - _Requirements: 1.2, 14.7_

  - [x] 16.2 Update Pomodoro session to carry active_task_id
    - When creating/resuming a PomodoroSession, set `active_task_id` from `Tracker.current_active_task_id`
    - _Requirements: 3.5_

- [x] 17. Checkpoint - Ensure all existing tests still pass after model/store changes
  - Run full test suite, fix any breakages from new fields
  - Update existing test fixtures to include new fields where needed

- [x] 18. Implement Focus Tab UI (web dashboard)
  - [x] 18.1 Update web API for Focus tab
    - `GET /api/todos` — return two-tier task list (High_Level_Tasks with nested Low_Level_Tasks)
    - `POST /api/todos` — create a new task (with optional `parent_id` for Low_Level_Task)
    - `POST /api/todos/<id>/toggle` — check off / uncheck a task
    - `DELETE /api/todos/<id>` — delete a task
    - `POST /api/todos/<id>/move` — move a Low_Level_Task to a different High_Level_Task
    - `POST /api/todos/merge` — merge two High_Level_Tasks
    - `POST /api/todos/clear-all` — delete all tasks
    - `POST /api/todos/clear-auto` — delete auto-generated tasks
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.9_

  - [x] 18.2 Add Current_Active_Task API
    - `POST /api/active-task` — set the Current_Active_Task by Low_Level_Task ID; updates Tracker and Pomodoro
    - `DELETE /api/active-task` — clear the Current_Active_Task
    - `GET /api/active-task` — return the current active task info
    - _Requirements: 13.5, 13.6, 13.7_

  - [x] 18.3 Update Focus tab frontend (dashboard.html + app.js)
    - Render two-tier task list: High_Level_Tasks as collapsible sections, Low_Level_Tasks as checkable items within
    - Add inline "Add task" input per High_Level_Task and a "Add bucket" input at the top
    - Implement drag-and-drop for Low_Level_Tasks between High_Level_Tasks
    - Clicking a Low_Level_Task sets it as Current_Active_Task (highlight + "● tracking" badge)
    - Show Pomodoro timer status tied to the Current_Active_Task
    - Do NOT show any auto-tracked activity details on this tab
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8_

- [x] 19. Implement Activity Tab UI (web dashboard)
  - [x] 19.1 Add Activity tab API endpoints
    - `GET /api/activity/by-task?date=YYYY-MM-DD` — return auto-tracked activities organized by High_Level_Task → Low_Level_Task → Activity_Entries, with time totals and summaries per entry
    - Each Activity_Entry includes: app_name, activity_summary, time_spent, timestamp range
    - Activities with no active_task_id grouped under "Unassigned"
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 19.2 Update Activity tab frontend (dashboard.html + app.js)
    - Render activity organized under user's task hierarchy: High_Level_Task sections → Low_Level_Task subsections → Activity_Entry list
    - Each Activity_Entry shows: app icon/name, human-readable summary, time spent (e.g., "12m")
    - Show total time per Low_Level_Task and per High_Level_Task
    - Collapsible sections for drill-down
    - "Unassigned" section at the bottom for activities with no active task
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 20. Update FlowTrackApp to wire Current_Active_Task
  - [x] 20.1 Add active task management to FlowTrackApp
    - Add `set_active_task(task_id)` method — sets `Tracker.current_active_task_id` and starts/switches Pomodoro session for that task
    - Add `clear_active_task()` method — clears `Tracker.current_active_task_id`
    - Wire the web API endpoints to these methods
    - _Requirements: 13.5, 13.6, 14.7_

- [x] 21. Checkpoint - Ensure all tests pass with new Focus/Activity features
  - Run full test suite
  - Verify Focus tab CRUD operations work end-to-end
  - Verify Activity tab displays auto-tracked work under correct tasks
  - Verify Current_Active_Task selection updates Pomodoro and activity association

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Tasks 1-13 are the original implementation (all completed)
- Tasks 14-21 implement the new Focus Tab and Activity Tab features
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The Focus tab is purely user-defined tasks (no auto-tracking shown)
- The Activity tab shows all auto-tracked work organized under the user's task hierarchy
- The Current_Active_Task bridges the two: user selects a task on Focus, auto-tracked work on Activity is associated with it
