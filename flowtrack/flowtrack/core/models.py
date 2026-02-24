"""Core data models for CarrotSummary.

Defines all dataclasses and enums used across the application:
- Window polling: WindowInfo
- Classification: ClassificationRule, ContextRule, ContextResult
- Pomodoro: SessionStatus, PomodoroSession
- Persistence: ActivityRecord
- Reporting: CategorySummary, DailySummary, WeeklySummary
- Email: SmtpConfig
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Window polling
# ---------------------------------------------------------------------------

@dataclass
class WindowInfo:
    """Information about the currently active window."""
    app_name: str
    window_title: str


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@dataclass
class ClassificationRule:
    """A rule that maps application/title patterns to a Work_Category."""
    app_patterns: list[str]    # regex patterns for app name
    title_patterns: list[str]  # regex patterns for window title
    category: str              # target Work_Category


@dataclass
class ContextRule:
    """A rule that refines a Work_Category into a Sub_Category."""
    category: str              # applies to this Work_Category
    title_patterns: list[str]  # regex patterns with named groups
    sub_category: str          # resulting sub-category


@dataclass
class ContextResult:
    """Result of context analysis for a window observation."""
    category: str        # Work_Category from Classifier
    sub_category: str    # refined sub-category (e.g., "Contract Draft")
    context_label: str   # human-readable label (e.g., "Contract Draft: Smith v. Jones")
    activity_summary: str = ""  # human-readable summary of what user is doing


# ---------------------------------------------------------------------------
# Pomodoro
# ---------------------------------------------------------------------------

class SessionStatus(Enum):
    """Status of a Pomodoro session."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    BREAK = "break"


@dataclass
class PomodoroSession:
    """A Pomodoro work/break session tied to a Work_Category."""
    id: str
    category: str
    sub_category: str
    start_time: datetime
    elapsed: timedelta
    status: SessionStatus
    completed_count: int  # number of completed work intervals in this session
    active_task_id: Optional[int] = None  # FK to focus_tasks Low_Level_Task


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

@dataclass
class ActivityRecord:
    """A single activity observation persisted to the database."""
    id: int
    timestamp: datetime
    app_name: str
    window_title: str
    category: str
    sub_category: str
    session_id: Optional[str]
    active_task_id: Optional[int] = None  # FK to focus_tasks Low_Level_Task
    activity_summary: str = ""  # human-readable summary from Context_Analyzer


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

@dataclass
class CategorySummary:
    """Aggregated time and session data for a single Work_Category."""
    category: str
    sub_categories: dict[str, timedelta] = field(default_factory=dict)  # sub_category -> time spent
    total_time: timedelta = field(default_factory=timedelta)
    completed_sessions: int = 0


@dataclass
class DailySummary:
    """Summary of activities for a single day."""
    date: date
    categories: list[CategorySummary] = field(default_factory=list)  # sorted by total_time descending
    total_time: timedelta = field(default_factory=timedelta)
    total_sessions: int = 0


@dataclass
class WeeklySummary:
    """Summary of activities for a 7-day period."""
    start_date: date
    end_date: date
    daily_breakdowns: list[DailySummary] = field(default_factory=list)
    categories: list[CategorySummary] = field(default_factory=list)  # aggregated for the week
    total_time: timedelta = field(default_factory=timedelta)
    total_sessions: int = 0


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

@dataclass
class SmtpConfig:
    """SMTP configuration for email delivery."""
    server: str
    port: int
    username: str
    password: str
    use_tls: bool
