"""Unit tests for SummaryGenerator."""

from datetime import date, datetime, timedelta

import pytest

from flowtrack.core.models import (
    ActivityRecord,
    CategorySummary,
    DailySummary,
    PomodoroSession,
    SessionStatus,
    WeeklySummary,
)
from flowtrack.persistence.store import ActivityStore
from flowtrack.reporting.summary import SummaryGenerator


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_store() -> ActivityStore:
    """Create an in-memory ActivityStore."""
    store = ActivityStore(":memory:")
    store.init_db()
    return store


def _activity(
    ts: datetime,
    category: str,
    sub_category: str = "",
    app: str = "App",
    title: str = "Title",
    session_id: str | None = None,
) -> ActivityRecord:
    return ActivityRecord(
        id=0,
        timestamp=ts,
        app_name=app,
        window_title=title,
        category=category,
        sub_category=sub_category,
        session_id=session_id,
    )


def _session(
    sid: str,
    category: str,
    start: datetime,
    status: SessionStatus = SessionStatus.COMPLETED,
    completed_count: int = 1,
    sub_category: str = "",
) -> PomodoroSession:
    return PomodoroSession(
        id=sid,
        category=category,
        sub_category=sub_category,
        start_time=start,
        elapsed=timedelta(minutes=25),
        status=status,
        completed_count=completed_count,
    )


DAY = date(2025, 6, 15)
MIDNIGHT = datetime(2025, 6, 15, 0, 0, 0)


# ------------------------------------------------------------------
# daily_summary — basic behaviour
# ------------------------------------------------------------------

class TestDailySummaryBasic:
    def test_empty_day_returns_zero_totals(self):
        store = _make_store()
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        assert ds.date == DAY
        assert ds.categories == []
        assert ds.total_time == timedelta()
        assert ds.total_sessions == 0

    def test_single_activity_counted(self):
        store = _make_store()
        store.save_activity(_activity(MIDNIGHT + timedelta(hours=9), "Dev"))
        gen = SummaryGenerator(store, poll_interval=5)
        ds = gen.daily_summary(DAY)

        assert len(ds.categories) == 1
        assert ds.categories[0].category == "Dev"
        assert ds.categories[0].total_time == timedelta(seconds=5)
        assert ds.total_time == timedelta(seconds=5)

    def test_multiple_activities_same_category(self):
        store = _make_store()
        for i in range(10):
            store.save_activity(
                _activity(MIDNIGHT + timedelta(hours=9, seconds=i * 5), "Dev")
            )
        gen = SummaryGenerator(store, poll_interval=5)
        ds = gen.daily_summary(DAY)

        assert ds.total_time == timedelta(seconds=50)
        assert ds.categories[0].total_time == timedelta(seconds=50)


# ------------------------------------------------------------------
# daily_summary — grouping and sorting
# ------------------------------------------------------------------

class TestDailySummaryGrouping:
    def test_groups_by_category(self):
        store = _make_store()
        for i in range(6):
            store.save_activity(
                _activity(MIDNIGHT + timedelta(hours=9, seconds=i * 5), "Dev")
            )
        for i in range(3):
            store.save_activity(
                _activity(MIDNIGHT + timedelta(hours=10, seconds=i * 5), "Email")
            )
        gen = SummaryGenerator(store, poll_interval=5)
        ds = gen.daily_summary(DAY)

        assert len(ds.categories) == 2
        cat_names = [c.category for c in ds.categories]
        assert "Dev" in cat_names
        assert "Email" in cat_names

    def test_sorted_by_total_time_descending(self):
        store = _make_store()
        # 2 activities for Email, 5 for Dev
        for i in range(5):
            store.save_activity(
                _activity(MIDNIGHT + timedelta(hours=9, seconds=i * 5), "Dev")
            )
        for i in range(2):
            store.save_activity(
                _activity(MIDNIGHT + timedelta(hours=10, seconds=i * 5), "Email")
            )
        gen = SummaryGenerator(store, poll_interval=5)
        ds = gen.daily_summary(DAY)

        assert ds.categories[0].category == "Dev"
        assert ds.categories[1].category == "Email"
        assert ds.categories[0].total_time >= ds.categories[1].total_time

    def test_sub_categories_tracked(self):
        store = _make_store()
        store.save_activity(
            _activity(MIDNIGHT + timedelta(hours=9), "Dev", sub_category="main.py")
        )
        store.save_activity(
            _activity(MIDNIGHT + timedelta(hours=9, seconds=5), "Dev", sub_category="test.py")
        )
        gen = SummaryGenerator(store, poll_interval=5)
        ds = gen.daily_summary(DAY)

        subs = ds.categories[0].sub_categories
        assert "main.py" in subs
        assert "test.py" in subs
        assert subs["main.py"] == timedelta(seconds=5)
        assert subs["test.py"] == timedelta(seconds=5)


# ------------------------------------------------------------------
# daily_summary — session counting
# ------------------------------------------------------------------

class TestDailySummarySessions:
    def test_completed_sessions_counted(self):
        store = _make_store()
        store.save_activity(_activity(MIDNIGHT + timedelta(hours=9), "Dev"))
        store.save_session(
            _session("s1", "Dev", MIDNIGHT + timedelta(hours=9), completed_count=2)
        )
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        assert ds.categories[0].completed_sessions == 2
        assert ds.total_sessions == 2

    def test_non_completed_sessions_excluded(self):
        store = _make_store()
        store.save_activity(_activity(MIDNIGHT + timedelta(hours=9), "Dev"))
        store.save_session(
            _session("s1", "Dev", MIDNIGHT + timedelta(hours=9), status=SessionStatus.ACTIVE)
        )
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        assert ds.total_sessions == 0

    def test_sessions_grouped_by_category(self):
        store = _make_store()
        store.save_activity(_activity(MIDNIGHT + timedelta(hours=9), "Dev"))
        store.save_activity(_activity(MIDNIGHT + timedelta(hours=10), "Email"))
        store.save_session(
            _session("s1", "Dev", MIDNIGHT + timedelta(hours=9), completed_count=1)
        )
        store.save_session(
            _session("s2", "Email", MIDNIGHT + timedelta(hours=10), completed_count=3)
        )
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        dev = next(c for c in ds.categories if c.category == "Dev")
        email = next(c for c in ds.categories if c.category == "Email")
        assert dev.completed_sessions == 1
        assert email.completed_sessions == 3
        assert ds.total_sessions == 4


# ------------------------------------------------------------------
# daily_summary — date filtering
# ------------------------------------------------------------------

class TestDailySummaryFiltering:
    def test_excludes_previous_day(self):
        store = _make_store()
        yesterday = MIDNIGHT - timedelta(hours=1)
        store.save_activity(_activity(yesterday, "Dev"))
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        assert ds.categories == []

    def test_excludes_next_day(self):
        store = _make_store()
        tomorrow = MIDNIGHT + timedelta(days=1, hours=1)
        store.save_activity(_activity(tomorrow, "Dev"))
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        assert ds.categories == []

    def test_includes_midnight_start(self):
        store = _make_store()
        store.save_activity(_activity(MIDNIGHT, "Dev"))
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        assert len(ds.categories) == 1

    def test_excludes_midnight_end(self):
        store = _make_store()
        # Exactly midnight of the next day should be excluded (half-open interval)
        next_midnight = MIDNIGHT + timedelta(days=1)
        store.save_activity(_activity(next_midnight, "Dev"))
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        assert ds.categories == []


# ------------------------------------------------------------------
# daily_summary — totals consistency
# ------------------------------------------------------------------

class TestDailySummaryTotals:
    def test_total_time_equals_sum_of_categories(self):
        store = _make_store()
        for i in range(4):
            store.save_activity(
                _activity(MIDNIGHT + timedelta(hours=9, seconds=i * 5), "Dev")
            )
        for i in range(3):
            store.save_activity(
                _activity(MIDNIGHT + timedelta(hours=10, seconds=i * 5), "Email")
            )
        gen = SummaryGenerator(store, poll_interval=5)
        ds = gen.daily_summary(DAY)

        cat_total = sum((c.total_time for c in ds.categories), timedelta())
        assert ds.total_time == cat_total

    def test_total_sessions_equals_sum_of_categories(self):
        store = _make_store()
        store.save_session(
            _session("s1", "Dev", MIDNIGHT + timedelta(hours=9), completed_count=2)
        )
        store.save_session(
            _session("s2", "Email", MIDNIGHT + timedelta(hours=10), completed_count=1)
        )
        gen = SummaryGenerator(store)
        ds = gen.daily_summary(DAY)

        cat_sessions = sum(c.completed_sessions for c in ds.categories)
        assert ds.total_sessions == cat_sessions


# ------------------------------------------------------------------
# weekly_summary
# ------------------------------------------------------------------

WEEK_START = date(2025, 6, 9)  # Monday


class TestWeeklySummary:
    def test_seven_daily_breakdowns(self):
        store = _make_store()
        gen = SummaryGenerator(store)
        ws = gen.weekly_summary(WEEK_START)

        assert len(ws.daily_breakdowns) == 7

    def test_correct_date_range(self):
        store = _make_store()
        gen = SummaryGenerator(store)
        ws = gen.weekly_summary(WEEK_START)

        assert ws.start_date == WEEK_START
        assert ws.end_date == WEEK_START + timedelta(days=6)

    def test_daily_dates_sequential(self):
        store = _make_store()
        gen = SummaryGenerator(store)
        ws = gen.weekly_summary(WEEK_START)

        for i, ds in enumerate(ws.daily_breakdowns):
            assert ds.date == WEEK_START + timedelta(days=i)

    def test_empty_week(self):
        store = _make_store()
        gen = SummaryGenerator(store)
        ws = gen.weekly_summary(WEEK_START)

        assert ws.total_time == timedelta()
        assert ws.total_sessions == 0
        assert ws.categories == []

    def test_aggregates_across_days(self):
        store = _make_store()
        # Day 1: 3 Dev activities
        day1 = datetime(2025, 6, 9, 10, 0, 0)
        for i in range(3):
            store.save_activity(
                _activity(day1 + timedelta(seconds=i * 5), "Dev")
            )
        # Day 3: 2 Dev activities
        day3 = datetime(2025, 6, 11, 14, 0, 0)
        for i in range(2):
            store.save_activity(
                _activity(day3 + timedelta(seconds=i * 5), "Dev")
            )
        gen = SummaryGenerator(store, poll_interval=5)
        ws = gen.weekly_summary(WEEK_START)

        assert len(ws.categories) == 1
        assert ws.categories[0].category == "Dev"
        assert ws.categories[0].total_time == timedelta(seconds=25)
        assert ws.total_time == timedelta(seconds=25)

    def test_weekly_total_time_equals_sum_of_daily(self):
        store = _make_store()
        day1 = datetime(2025, 6, 9, 10, 0, 0)
        for i in range(4):
            store.save_activity(
                _activity(day1 + timedelta(seconds=i * 5), "Dev")
            )
        day2 = datetime(2025, 6, 10, 11, 0, 0)
        for i in range(2):
            store.save_activity(
                _activity(day2 + timedelta(seconds=i * 5), "Email")
            )
        gen = SummaryGenerator(store, poll_interval=5)
        ws = gen.weekly_summary(WEEK_START)

        daily_total = sum(
            (ds.total_time for ds in ws.daily_breakdowns), timedelta()
        )
        assert ws.total_time == daily_total

    def test_weekly_total_sessions_equals_sum_of_daily(self):
        store = _make_store()
        store.save_session(
            _session("s1", "Dev", datetime(2025, 6, 9, 9, 0), completed_count=2)
        )
        store.save_session(
            _session("s2", "Dev", datetime(2025, 6, 11, 9, 0), completed_count=1)
        )
        gen = SummaryGenerator(store)
        ws = gen.weekly_summary(WEEK_START)

        daily_sessions = sum(ds.total_sessions for ds in ws.daily_breakdowns)
        assert ws.total_sessions == daily_sessions
        assert ws.total_sessions == 3

    def test_weekly_categories_sorted_descending(self):
        store = _make_store()
        day1 = datetime(2025, 6, 9, 10, 0, 0)
        # 5 Dev, 2 Email
        for i in range(5):
            store.save_activity(
                _activity(day1 + timedelta(seconds=i * 5), "Dev")
            )
        for i in range(2):
            store.save_activity(
                _activity(day1 + timedelta(minutes=30, seconds=i * 5), "Email")
            )
        gen = SummaryGenerator(store, poll_interval=5)
        ws = gen.weekly_summary(WEEK_START)

        assert ws.categories[0].category == "Dev"
        assert ws.categories[1].category == "Email"


# ------------------------------------------------------------------
# Configurable poll_interval
# ------------------------------------------------------------------

class TestPollInterval:
    def test_custom_poll_interval(self):
        store = _make_store()
        store.save_activity(_activity(MIDNIGHT + timedelta(hours=9), "Dev"))
        gen = SummaryGenerator(store, poll_interval=10)
        ds = gen.daily_summary(DAY)

        assert ds.total_time == timedelta(seconds=10)

    def test_default_poll_interval_is_5(self):
        gen = SummaryGenerator(_make_store())
        assert gen.poll_interval == 5
