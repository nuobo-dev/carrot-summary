# Requirements Document

## Introduction

FlowTrack is a cross-platform (macOS and Windows) productivity tracking application that monitors active window titles, automatically categorizes work into meaningful buckets, integrates a Pomodoro timer that adapts to context switches, and generates daily and weekly work summaries. The application prioritizes privacy by abstracting window titles into high-level work categories rather than capturing sensitive content.

The application features a two-tier user-defined task system: users create high-level tasks (buckets) containing low-level sub-tasks, then select a "Current Active Task" to focus on. All auto-tracked window activity is associated with the currently active task, providing a clear picture of what work was done under each task.

## Glossary

- **Tracker**: The core component that polls the active window title at regular intervals using platform-specific APIs (macOS: AppleScript/Accessibility API, Windows: Win32 API) and records activity observations.
- **Classifier**: The component that maps a window title and application name to a Work_Category using keyword-based rules.
- **Work_Category**: A high-level label representing a type of work (e.g., "Document Editing", "Email & Communication", "Meetings", "Research & Browsing", "Spreadsheets", "Presentations", "Project Management", "Creative Tools", "Development", "Other"). Categories are configurable to suit any profession.
- **Pomodoro_Session**: A timed work interval associated with the Current_Active_Task, following the standard Pomodoro technique (25 minutes of work, 5-minute short break, 15-minute long break after 4 sessions).
- **Pomodoro_Manager**: The component responsible for creating, switching, and completing Pomodoro sessions based on the user's active task selection.
- **Context_Switch**: A detected change in the active Work_Category that persists beyond a configurable debounce threshold.
- **Activity_Log**: A timestamped record of an observed activity stored in the local SQLite database, associated with the Current_Active_Task.
- **Summary_Generator**: The component that queries Activity_Logs and Pomodoro_Sessions to produce human-readable daily and weekly reports.
- **Report_Exporter**: The component that converts weekly summary data into a Word document (.docx) format for distribution.
- **Email_Sender**: The component that sends the exported weekly report to a user-configured email address via SMTP.
- **Debounce_Threshold**: A configurable time duration (default 30 seconds) that a new Work_Category must persist before the system recognizes it as a Context_Switch.
- **Context_Analyzer**: The component that examines window titles within an application to infer the specific work context (e.g., distinguishing a "Design Doc" from "Meeting Notes" within the same editor application) and assigns a sub-category.
- **Sub_Category**: A more specific label within a Work_Category that describes the particular document, project, or task being worked on (e.g., "Design Doc: Project X" within the "Design Docs" Work_Category).
- **High_Level_Task**: A user-defined top-level task bucket in the Focus tab (e.g., "Tickets", "Design Work", "Code Reviews"). Acts as a grouping container for Low_Level_Tasks.
- **Low_Level_Task**: A user-defined sub-task within a High_Level_Task (e.g., "authentication issue" under "Tickets"). Can be checked off as done. Can be dragged between High_Level_Tasks.
- **Current_Active_Task**: The Low_Level_Task (displayed as "High_Level: Low_Level") that the user has clicked to begin tracking. The Pomodoro timer runs against this task, and all auto-tracked activities are associated with it.
- **Activity_Entry**: An auto-tracked record of detailed work performed under a Low_Level_Task, including the application used, a summary of what the user did, and time spent (e.g., "Tickets portal: researched authentication issue, documented findings — 12m").

## Requirements

### Requirement 1: Active Window Polling

**User Story:** As a user, I want FlowTrack to monitor which application and window I am actively using, so that my work activities are captured automatically without manual input.

#### Acceptance Criteria

1. WHEN FlowTrack is running, THE Tracker SHALL poll the active window title and application name at a configurable interval (default 5 seconds) using platform-specific APIs (macOS: AppleScript/Accessibility API, Windows: Win32 API).
2. WHEN the Tracker retrieves a window title, THE Tracker SHALL record an Activity_Log entry containing the timestamp, application name, window title, derived Work_Category, and the Current_Active_Task identifier.
3. IF the platform window API is unavailable or returns an error, THEN THE Tracker SHALL log the error and continue polling on the next interval without crashing.
4. WHEN the user's screen is locked or the system is idle, THE Tracker SHALL pause activity recording and resume when the user becomes active again.
5. THE Tracker SHALL provide a consistent interface across macOS and Windows, abstracting platform-specific window polling behind a common API.

### Requirement 2: Activity Classification

**User Story:** As a user, I want my activities to be automatically classified into meaningful work categories, so that I can understand how I spend my time without manually tagging each activity.

#### Acceptance Criteria

1. WHEN the Tracker provides a window title and application name, THE Classifier SHALL return exactly one Work_Category from the predefined set.
2. THE Classifier SHALL use configurable keyword-based rules to map application names and window title patterns to Work_Categories.
3. WHEN no keyword rule matches a given window title and application name, THE Classifier SHALL assign the Work_Category "Other".
4. WHEN the user adds or modifies classification rules in the configuration, THE Classifier SHALL apply the updated rules to subsequent activity observations without requiring a restart.
5. THE Classifier SHALL serialize classification rules to a JSON configuration file and deserialize them on startup, preserving all rule definitions through a round-trip.

### Requirement 9: In-App Context Awareness

**User Story:** As a user, I want FlowTrack to understand the context of what I'm working on within an application, so that different documents or tasks in the same app are bucketed into distinct work categories.

#### Acceptance Criteria

1. WHEN the Tracker captures a window title, THE Context_Analyzer SHALL extract contextual cues from the title (e.g., document name, file path, project name, URL, case number) to determine the specific work context.
2. WHEN a user is working in a document editor (e.g., Word, Google Docs, Pages), THE Context_Analyzer SHALL infer the document's purpose from the window title and classify it into a specific Sub_Category (e.g., "Contract Draft", "Meeting Notes", "Design Brief", "Status Report").
3. WHEN a user is working in a browser with multiple tabs, THE Context_Analyzer SHALL use the active tab title to distinguish between different work contexts (e.g., "Research", "Project Management", "Client Portal", "Email").
4. WHEN a user is working in a specialized professional tool (e.g., IDE, Figma, AutoCAD, legal research database, spreadsheet), THE Context_Analyzer SHALL extract the project or document name from the window title to associate the activity with a specific work context.
5. THE Context_Analyzer SHALL use configurable pattern-matching rules that map window title patterns to Sub_Categories, allowing users of any profession to customize context detection for their workflows.
6. WHEN the Context_Analyzer cannot determine a specific Sub_Category from the window title, THE Context_Analyzer SHALL fall back to the application-level Work_Category provided by the Classifier.

### Requirement 3: Pomodoro Timer

**User Story:** As a user, I want an integrated Pomodoro timer that tracks my focused work intervals against my currently active task, so that I can maintain productive work habits with structured breaks.

#### Acceptance Criteria

1. THE Pomodoro_Manager SHALL use standard Pomodoro intervals: 25-minute work sessions, 5-minute short breaks, and 15-minute long breaks after every 4 completed work sessions.
2. WHEN a Pomodoro_Session work interval completes, THE Pomodoro_Manager SHALL mark the session as complete and begin a break interval.
3. WHEN a break interval completes, THE Pomodoro_Manager SHALL signal readiness for the next work session.
4. THE Pomodoro_Manager SHALL track the count of completed Pomodoro_Sessions to determine when a long break is due.
5. THE Pomodoro_Manager SHALL associate each Pomodoro_Session with the Current_Active_Task selected by the user.

### Requirement 4: Automatic Context Switch Detection

**User Story:** As a user, I want FlowTrack to detect when I switch between different types of work and automatically manage my Pomodoro sessions, so that each work category is tracked independently.

#### Acceptance Criteria

1. WHEN the Classifier assigns a Work_Category that differs from the current Pomodoro_Session's category, THE Pomodoro_Manager SHALL start a Debounce_Threshold timer before recognizing a Context_Switch.
2. WHEN the new Work_Category persists beyond the Debounce_Threshold, THE Pomodoro_Manager SHALL pause the current Pomodoro_Session and start a new Pomodoro_Session for the new Work_Category.
3. WHEN the user returns to a previously paused Work_Category, THE Pomodoro_Manager SHALL resume the existing paused Pomodoro_Session for that category rather than creating a new one.
4. IF the Work_Category reverts to the original category before the Debounce_Threshold expires, THEN THE Pomodoro_Manager SHALL cancel the pending Context_Switch and continue the current session.

### Requirement 5: Activity Persistence

**User Story:** As a user, I want my activity data to be stored reliably on my local machine, so that I can review my work history and generate summaries at any time.

#### Acceptance Criteria

1. THE Activity_Log SHALL persist all activity records to a local SQLite database.
2. WHEN an Activity_Log entry is written, THE Activity_Log SHALL store the timestamp, application name, window title, Work_Category, associated Pomodoro_Session identifier, and the Current_Active_Task identifier (high-level task ID and low-level task ID).
3. WHEN a Pomodoro_Session is created or updated, THE Pomodoro_Manager SHALL persist the session state (category, start time, elapsed time, status) to the SQLite database.
4. FOR ALL valid Activity_Log entries, writing then reading from the database SHALL produce an equivalent record (round-trip property).

### Requirement 6: Daily Summaries

**User Story:** As a user, I want to see a summary of my daily work activities, so that I can reflect on how I spent my day and identify productivity patterns.

#### Acceptance Criteria

1. WHEN the user requests a daily summary for a given date, THE Summary_Generator SHALL produce a report covering all Activity_Logs and Pomodoro_Sessions for that date.
2. THE Summary_Generator SHALL group activities by Work_Category and display the total time spent in each category.
3. THE Summary_Generator SHALL display the number of completed Pomodoro_Sessions per Work_Category.
4. THE Summary_Generator SHALL sort categories by total time spent in descending order.

### Requirement 7: Weekly Summaries

**User Story:** As a user, I want to see a summary of my weekly work activities, so that I can understand my productivity trends over a longer period.

#### Acceptance Criteria

1. WHEN the user requests a weekly summary, THE Summary_Generator SHALL produce a report covering all Activity_Logs and Pomodoro_Sessions for the specified 7-day period.
2. THE Summary_Generator SHALL include a day-by-day breakdown of time spent per Work_Category.
3. THE Summary_Generator SHALL display the total number of completed Pomodoro_Sessions for the week.
4. THE Summary_Generator SHALL display the total tracked time for the week.

### Requirement 8: Summary Formatting

**User Story:** As a user, I want my summaries to be presented in a clear, human-readable format, so that I can quickly understand my productivity data.

#### Acceptance Criteria

1. THE Summary_Generator SHALL format summaries as plain text with aligned columns for category names, time durations, and session counts.
2. THE Summary_Generator SHALL format time durations in hours and minutes (e.g., "2h 15m").
3. FOR ALL valid summary data, formatting then parsing the time duration strings SHALL produce equivalent duration values (round-trip property).

### Requirement 10: Weekly Report Export and Email Delivery

**User Story:** As a user, I want my weekly summary to be automatically exported as a Word document and emailed to me, so that I have a professional report delivered to my inbox without manual effort.

#### Acceptance Criteria

1. WHEN a weekly summary is generated, THE Report_Exporter SHALL convert the summary data into a formatted Word document (.docx) containing category breakdowns, time totals, session counts, and day-by-day details.
2. THE Report_Exporter SHALL include a title page with the report date range and the user's configured name.
3. WHEN the user has configured an email address in the application settings, THE Email_Sender SHALL send the generated Word document as an attachment to that email address.
4. THE Email_Sender SHALL use user-configured SMTP settings (server, port, credentials) to deliver the email.
5. IF the email delivery fails, THEN THE Email_Sender SHALL log the error and retain the generated Word document locally for manual retrieval.
6. WHEN the user has not configured an email address, THE Report_Exporter SHALL save the Word document to a configurable local directory.

### Requirement 11: Downloadable Desktop Application

**User Story:** As a user, I want to download and install FlowTrack as a standalone desktop application, so that I can use it without needing to install Python or manage dependencies.

#### Acceptance Criteria

1. THE FlowTrack application SHALL be packaged as a standalone executable that runs without requiring a Python installation on the user's machine.
2. THE FlowTrack application SHALL provide a system tray icon with a menu for starting/stopping tracking, viewing summaries, opening configuration, and quitting.
3. WHEN the application is launched, THE FlowTrack application SHALL start tracking in the background and display a system tray icon.
4. THE FlowTrack application SHALL store user data (database, configuration) in platform-appropriate directories (macOS: ~/Library/Application Support/FlowTrack, Windows: %APPDATA%/FlowTrack).
5. WHEN the application is launched for the first time, THE FlowTrack application SHALL create a default configuration file with sensible defaults.
6. THE FlowTrack application SHALL be distributable as a .dmg disk image on macOS and a .zip or installer on Windows.

### Requirement 12: Settings User Interface

**User Story:** As a user, I want a graphical settings interface to configure email delivery, customize work categories, and adjust Pomodoro settings, so that I can personalize FlowTrack without editing configuration files.

#### Acceptance Criteria

1. WHEN the user selects "Settings" from the system tray menu, THE FlowTrack application SHALL display a settings window with tabs for Email, Categories, Context Rules, and Pomodoro.
2. WHEN the user configures email settings (SMTP server, port, credentials, recipient address) in the Email tab, THE FlowTrack application SHALL validate the SMTP connection and save the settings to the configuration file.
3. WHEN the user adds, edits, or removes Work_Categories and their associated keyword rules in the Categories tab, THE Classifier SHALL apply the updated rules immediately without requiring a restart.
4. WHEN the user adds, edits, or removes Context Rules (Sub_Category patterns) in the Context Rules tab, THE Context_Analyzer SHALL apply the updated rules immediately without requiring a restart.
5. THE settings window SHALL pre-populate all fields with the current configuration values when opened.
6. WHEN the user saves settings, THE FlowTrack application SHALL persist all changes to the configuration file and apply them to the running application.

### Requirement 13: Focus Tab — User-Defined Task List

**User Story:** As a user, I want a simple two-tier task list on the Focus tab where I define my own high-level and low-level tasks, so that I can organize my work and track Pomodoro sessions against specific tasks.

#### Acceptance Criteria

1. THE Focus tab SHALL display a two-tier task list where each High_Level_Task contains zero or more Low_Level_Tasks.
2. THE user SHALL be able to create, rename, and delete High_Level_Tasks and Low_Level_Tasks.
3. THE user SHALL be able to drag and drop Low_Level_Tasks between High_Level_Tasks to reorganize work.
4. THE user SHALL be able to check off (mark as done) individual Low_Level_Tasks.
5. WHEN the user clicks on a Low_Level_Task, THE application SHALL set it as the Current_Active_Task, displayed as "High_Level: Low_Level" (e.g., "Tickets: authentication issue").
6. WHEN a Current_Active_Task is set, THE Pomodoro timer SHALL run against that task and all auto-tracked activities SHALL be associated with it.
7. THE Focus tab SHALL visually indicate which task is the Current_Active_Task (e.g., highlight, "● tracking" badge).
8. THE Focus tab SHALL NOT display auto-tracked activity details — it is purely a user-defined task list with Pomodoro tracking status.
9. THE task list SHALL persist across application restarts via the SQLite database.

### Requirement 14: Activity Tab — Auto-Tracked Work Under User Tasks

**User Story:** As a user, I want the Activity tab to show all my auto-tracked work organized under my user-defined task hierarchy, so that I can see exactly what I did for each task.

#### Acceptance Criteria

1. THE Activity tab SHALL display auto-tracked activities organized under the user's two-tier task hierarchy: High_Level_Task → Low_Level_Task → Activity_Entries.
2. EACH Activity_Entry SHALL show the application name, a human-readable summary of what the user did (derived from window titles and context analysis), and the time spent on that activity.
3. THE Activity_Entry summary SHALL be generated by the Context_Analyzer from window title patterns (e.g., "Tickets portal: researched authentication issue, documented findings").
4. WHEN the user has no Current_Active_Task set, auto-tracked activities SHALL be grouped under an "Unassigned" section.
5. THE Activity tab SHALL show the total time spent on each Low_Level_Task (sum of its Activity_Entries) and each High_Level_Task (sum of its Low_Level_Tasks).
6. THE Activity tab SHALL allow the user to expand/collapse High_Level_Tasks and Low_Level_Tasks to drill into detail.
7. WHEN the user switches the Current_Active_Task, subsequent auto-tracked activities SHALL be associated with the newly selected task.

