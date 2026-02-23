"""Unit tests for ActivityStore."""

import pytest
from datetime import datetime, timedelta

from flowtrack.core.models import ActivityRecord, PomodoroSession, SessionStatus
from flowtrack.persistence.store import ActivityStore


@pytest.fixture
def store():
    """Create an in-memory ActivityStore for each test."""
    s = ActivityStore(":memory:")
    s.init_db()
    yield s
    s.close()


# ------------------------------------------------------------------
# Schema / init_db
# ------------------------------------------------------------------

def test_init_db_creates_tables(store: ActivityStore):
    conn = store._get_conn()
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "activity_logs" in tables
    assert "pomodoro_sessions" in tables


def test_init_db_creates_indexes(store: ActivityStore):
    conn = store._get_conn()
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_activity_timestamp" in indexes
    assert "idx_session_start" in indexes


def test_init_db_idempotent(store: ActivityStore):
    """Calling init_db twice should not raise."""
    store.init_db()


# ------------------------------------------------------------------
# Activity record round-trip
# ------------------------------------------------------------------

def _make_activity(**overrides) -> ActivityRecord:
    defaults = dict(
        id=0,
        timestamp=datetime(2025, 1, 15, 10, 30, 0),
        app_name="VS Code",
        window_title="models.py — FlowTrack",
        category="Development",
        sub_category="FlowTrack",
        session_id="sess-001",
    )
    defaults.update(overrides)
    return ActivityRecord(**defaults)


def test_save_and_get_activity_by_id(store: ActivityStore):
    record = _make_activity()
    row_id = store.save_activity(record)
    loaded = store.get_activity_by_id(row_id)

    assert loaded is not None
    assert loaded.id == row_id
    assert loaded.timestamp == record.timestamp
    assert loaded.app_name == record.app_name
    assert loaded.window_title == record.window_title
    assert loaded.category == record.category
    assert loaded.sub_category == record.sub_category
    assert loaded.session_id == record.session_id


def test_get_activity_by_id_missing(store: ActivityStore):
    assert store.get_activity_by_id(9999) is None


def test_save_activity_with_none_session_id(store: ActivityStore):
    record = _make_activity(session_id=None)
    row_id = store.save_activity(record)
    loaded = store.get_activity_by_id(row_id)
    assert loaded is not None
    assert loaded.session_id is None


def test_get_activities_filters_by_range(store: ActivityStore):
    t1 = datetime(2025, 1, 15, 8, 0, 0)
    t2 = datetime(2025, 1, 15, 12, 0, 0)
    t3 = datetime(2025, 1, 16, 9, 0, 0)

    store.save_activity(_make_activity(timestamp=t1))
    store.save_activity(_make_activity(timestamp=t2))
    store.save_activity(_make_activity(timestamp=t3))

    start = datetime(2025, 1, 15, 0, 0, 0)
    end = datetime(2025, 1, 16, 0, 0, 0)
    results = store.get_activities(start, end)

    assert len(results) == 2
    assert results[0].timestamp == t1
    assert results[1].timestamp == t2


def test_get_activities_empty_range(store: ActivityStore):
    store.save_activity(_make_activity())
    results = store.get_activities(
        datetime(2024, 1, 1), datetime(2024, 1, 2)
    )
    assert results == []


# ------------------------------------------------------------------
# Pomodoro session round-trip
# ------------------------------------------------------------------

def _make_session(**overrides) -> PomodoroSession:
    defaults = dict(
        id="pomo-001",
        category="Development",
        sub_category="FlowTrack",
        start_time=datetime(2025, 1, 15, 10, 0, 0),
        elapsed=timedelta(minutes=12, seconds=30),
        status=SessionStatus.ACTIVE,
        completed_count=2,
    )
    defaults.update(overrides)
    return PomodoroSession(**defaults)


def test_save_and_get_session_by_id(store: ActivityStore):
    session = _make_session()
    store.save_session(session)
    loaded = store.get_session_by_id("pomo-001")

    assert loaded is not None
    assert loaded.id == session.id
    assert loaded.category == session.category
    assert loaded.sub_category == session.sub_category
    assert loaded.start_time == session.start_time
    assert loaded.elapsed == session.elapsed
    assert loaded.status == session.status
    assert loaded.completed_count == session.completed_count


def test_get_session_by_id_missing(store: ActivityStore):
    assert store.get_session_by_id("nonexistent") is None


def test_save_session_upsert(store: ActivityStore):
    session = _make_session(elapsed=timedelta(minutes=5))
    store.save_session(session)

    updated = _make_session(elapsed=timedelta(minutes=20), status=SessionStatus.PAUSED)
    store.save_session(updated)

    loaded = store.get_session_by_id("pomo-001")
    assert loaded is not None
    assert loaded.elapsed == timedelta(minutes=20)
    assert loaded.status == SessionStatus.PAUSED


def test_get_sessions_filters_by_range(store: ActivityStore):
    t1 = datetime(2025, 1, 15, 8, 0, 0)
    t2 = datetime(2025, 1, 15, 14, 0, 0)
    t3 = datetime(2025, 1, 16, 9, 0, 0)

    store.save_session(_make_session(id="s1", start_time=t1))
    store.save_session(_make_session(id="s2", start_time=t2))
    store.save_session(_make_session(id="s3", start_time=t3))

    start = datetime(2025, 1, 15, 0, 0, 0)
    end = datetime(2025, 1, 16, 0, 0, 0)
    results = store.get_sessions(start, end)

    assert len(results) == 2
    assert results[0].id == "s1"
    assert results[1].id == "s2"


def test_get_sessions_empty_range(store: ActivityStore):
    store.save_session(_make_session())
    results = store.get_sessions(
        datetime(2024, 1, 1), datetime(2024, 1, 2)
    )
    assert results == []


def test_session_all_statuses(store: ActivityStore):
    """Every SessionStatus value should survive a round-trip."""
    for status in SessionStatus:
        sid = f"status-{status.value}"
        store.save_session(_make_session(id=sid, status=status))
        loaded = store.get_session_by_id(sid)
        assert loaded is not None
        assert loaded.status == status


def test_activity_preserves_empty_sub_category(store: ActivityStore):
    record = _make_activity(sub_category="")
    row_id = store.save_activity(record)
    loaded = store.get_activity_by_id(row_id)
    assert loaded is not None
    assert loaded.sub_category == ""


def test_session_zero_elapsed(store: ActivityStore):
    session = _make_session(elapsed=timedelta(0))
    store.save_session(session)
    loaded = store.get_session_by_id(session.id)
    assert loaded is not None
    assert loaded.elapsed == timedelta(0)
