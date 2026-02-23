# Implementation Plan: FlowTrack

## Overview

Build FlowTrack as a cross-platform Python desktop app with system tray UI, automatic activity tracking, Pomodoro management, and weekly report export. Implementation proceeds bottom-up: data models and persistence first, then core logic, then reporting, then UI and packaging.

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

- [x] 10. Implement UI layer
  - [x] 10.1 Implement Settings Window
    - Create `flowtrack/ui/settings.py` with `SettingsWindow` class using tkinter + ttk
    - Build Email tab (SMTP config + test connection button)
    - Build Categories tab (add/edit/remove Work_Categories and keyword rules)
    - Build Context Rules tab (add/edit/remove Sub_Category patterns)
    - Build Pomodoro tab (durations, debounce, manual task creation)
    - Apply minimalistic ttk.Style theme (muted colors, flat design, system fonts)
    - Pre-populate fields from current config, save and apply on confirm
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 10.2 Implement System Tray Application
    - Create `flowtrack/ui/app.py` with `FlowTrackApp` class
    - Use pystray for system tray icon with menu: Start/Stop, Daily Summary, Weekly Report, Add Task, Settings, Quit
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

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- Implementation proceeds bottom-up: models → persistence → core logic → reporting → UI → packaging
