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
    assert "focus_tasks" in tables


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
    assert "idx_activity_task" in indexes
    assert "idx_focus_parent" in indexes


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
        window_title="models.py — CarrotSummary",
        category="Development",
        sub_category="CarrotSummary",
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
        sub_category="CarrotSummary",
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


# ------------------------------------------------------------------
# active_task_id and activity_summary round-trips
# ------------------------------------------------------------------

def test_activity_round_trips_active_task_id(store: ActivityStore):
    record = _make_activity(active_task_id=42, activity_summary="edited design doc")
    row_id = store.save_activity(record)
    loaded = store.get_activity_by_id(row_id)
    assert loaded is not None
    assert loaded.active_task_id == 42
    assert loaded.activity_summary == "edited design doc"


def test_activity_round_trips_null_active_task_id(store: ActivityStore):
    record = _make_activity(active_task_id=None, activity_summary="")
    row_id = store.save_activity(record)
    loaded = store.get_activity_by_id(row_id)
    assert loaded is not None
    assert loaded.active_task_id is None
    assert loaded.activity_summary == ""


def test_get_activities_includes_new_fields(store: ActivityStore):
    t = datetime(2025, 1, 15, 10, 0, 0)
    store.save_activity(_make_activity(timestamp=t, active_task_id=7, activity_summary="reviewed PR"))
    results = store.get_activities(datetime(2025, 1, 15), datetime(2025, 1, 16))
    assert len(results) == 1
    assert results[0].active_task_id == 7
    assert results[0].activity_summary == "reviewed PR"


def test_session_round_trips_active_task_id(store: ActivityStore):
    session = _make_session(active_task_id=99)
    store.save_session(session)
    loaded = store.get_session_by_id(session.id)
    assert loaded is not None
    assert loaded.active_task_id == 99


def test_session_round_trips_null_active_task_id(store: ActivityStore):
    session = _make_session(active_task_id=None)
    store.save_session(session)
    loaded = store.get_session_by_id(session.id)
    assert loaded is not None
    assert loaded.active_task_id is None


def test_get_sessions_includes_active_task_id(store: ActivityStore):
    t = datetime(2025, 1, 15, 10, 0, 0)
    store.save_session(_make_session(id="s-task", start_time=t, active_task_id=5))
    results = store.get_sessions(datetime(2025, 1, 15), datetime(2025, 1, 16))
    assert len(results) == 1
    assert results[0].active_task_id == 5


# ------------------------------------------------------------------
# focus_tasks table and cascade delete
# ------------------------------------------------------------------

def test_focus_tasks_cascade_delete(store: ActivityStore):
    """Deleting a parent task should cascade-delete its children."""
    parent_id = store.add_todo("Parent", "Work")
    store.add_todo("Child 1", "Work", parent_id=parent_id)
    store.add_todo("Child 2", "Work", parent_id=parent_id)
    assert len(store.get_todos(include_done=True)) == 3
    store.delete_todo(parent_id)
    assert len(store.get_todos(include_done=True)) == 0


def test_foreign_keys_enabled(store: ActivityStore):
    conn = store._get_conn()
    result = conn.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1


# ------------------------------------------------------------------
# Focus task CRUD operations (Task 14.5)
# ------------------------------------------------------------------


class TestAddTodo:
    """Tests for add_todo()."""

    def test_add_high_level_task(self, store: ActivityStore):
        """A task with no parent_id is a High_Level_Task."""
        task_id = store.add_todo("Tickets", "Work")
        todos = store.get_todos(include_done=True)
        task = next(t for t in todos if t["id"] == task_id)
        assert task["title"] == "Tickets"
        assert task["category"] == "Work"
        assert task["parent_id"] is None
        assert task["done"] == 0

    def test_add_low_level_task(self, store: ActivityStore):
        """A task with parent_id is a Low_Level_Task."""
        parent_id = store.add_todo("Tickets", "Work")
        child_id = store.add_todo("auth issue", "Work", parent_id=parent_id)
        todos = store.get_todos(include_done=True)
        child = next(t for t in todos if t["id"] == child_id)
        assert child["title"] == "auth issue"
        assert child["parent_id"] == parent_id

    def test_add_auto_generated_task(self, store: ActivityStore):
        """Auto-generated tasks have auto_generated=1."""
        task_id = store.add_todo("Auto Task", "Work", auto=True)
        todos = store.get_todos(include_done=True)
        task = next(t for t in todos if t["id"] == task_id)
        assert task["auto_generated"] == 1

    def test_add_returns_unique_ids(self, store: ActivityStore):
        """Each add_todo call returns a unique id."""
        id1 = store.add_todo("Task 1")
        id2 = store.add_todo("Task 2")
        assert id1 != id2

    def test_add_with_empty_category(self, store: ActivityStore):
        """Category defaults to empty string."""
        task_id = store.add_todo("No Category")
        todos = store.get_todos(include_done=True)
        task = next(t for t in todos if t["id"] == task_id)
        assert task["category"] == ""

    def test_add_sets_created_at(self, store: ActivityStore):
        """created_at should be a valid ISO timestamp."""
        task_id = store.add_todo("Timestamped")
        todos = store.get_todos(include_done=True)
        task = next(t for t in todos if t["id"] == task_id)
        # Should not raise
        datetime.fromisoformat(task["created_at"])


class TestGetTodos:
    """Tests for get_todos()."""

    def test_empty_store(self, store: ActivityStore):
        """No tasks returns empty list."""
        assert store.get_todos() == []
        assert store.get_todos(include_done=True) == []

    def test_excludes_done_by_default(self, store: ActivityStore):
        """get_todos() without include_done skips done tasks."""
        id1 = store.add_todo("Active")
        id2 = store.add_todo("Done")
        store.toggle_todo(id2)
        todos = store.get_todos(include_done=False)
        ids = [t["id"] for t in todos]
        assert id1 in ids
        assert id2 not in ids

    def test_includes_done_when_requested(self, store: ActivityStore):
        """get_todos(include_done=True) returns all tasks."""
        id1 = store.add_todo("Active")
        id2 = store.add_todo("Done")
        store.toggle_todo(id2)
        todos = store.get_todos(include_done=True)
        ids = [t["id"] for t in todos]
        assert id1 in ids
        assert id2 in ids

    def test_returns_parent_child_structure(self, store: ActivityStore):
        """Both parent and child tasks are returned with parent_id info."""
        parent_id = store.add_todo("Bucket")
        child_id = store.add_todo("Sub-task", parent_id=parent_id)
        todos = store.get_todos(include_done=True)
        parent = next(t for t in todos if t["id"] == parent_id)
        child = next(t for t in todos if t["id"] == child_id)
        assert parent["parent_id"] is None
        assert child["parent_id"] == parent_id

    def test_returns_all_fields(self, store: ActivityStore):
        """Each dict has all expected keys."""
        store.add_todo("Test", "Cat", auto=True)
        todos = store.get_todos(include_done=True)
        task = todos[0]
        expected_keys = {"id", "title", "category", "parent_id", "done",
                         "auto_generated", "created_at", "sort_order"}
        assert expected_keys.issubset(set(task.keys()))


class TestToggleTodo:
    """Tests for toggle_todo()."""

    def test_toggle_marks_done(self, store: ActivityStore):
        """First toggle sets done=1."""
        task_id = store.add_todo("Toggle me")
        store.toggle_todo(task_id)
        todos = store.get_todos(include_done=True)
        task = next(t for t in todos if t["id"] == task_id)
        assert task["done"] == 1

    def test_toggle_twice_restores(self, store: ActivityStore):
        """Toggling twice returns to done=0."""
        task_id = store.add_todo("Toggle me")
        store.toggle_todo(task_id)
        store.toggle_todo(task_id)
        todos = store.get_todos(include_done=True)
        task = next(t for t in todos if t["id"] == task_id)
        assert task["done"] == 0

    def test_toggle_only_affects_target(self, store: ActivityStore):
        """Toggling one task doesn't affect others."""
        id1 = store.add_todo("Task 1")
        id2 = store.add_todo("Task 2")
        store.toggle_todo(id1)
        todos = store.get_todos(include_done=True)
        t1 = next(t for t in todos if t["id"] == id1)
        t2 = next(t for t in todos if t["id"] == id2)
        assert t1["done"] == 1
        assert t2["done"] == 0


class TestDeleteTodo:
    """Tests for delete_todo()."""

    def test_delete_single_task(self, store: ActivityStore):
        """Deleting a task removes it."""
        task_id = store.add_todo("Delete me")
        store.delete_todo(task_id)
        assert store.get_todos(include_done=True) == []

    def test_delete_parent_cascades_children(self, store: ActivityStore):
        """Deleting a High_Level_Task cascade-deletes its Low_Level_Tasks."""
        parent_id = store.add_todo("Parent")
        store.add_todo("Child 1", parent_id=parent_id)
        store.add_todo("Child 2", parent_id=parent_id)
        store.delete_todo(parent_id)
        assert store.get_todos(include_done=True) == []

    def test_delete_child_preserves_parent(self, store: ActivityStore):
        """Deleting a Low_Level_Task doesn't affect the parent."""
        parent_id = store.add_todo("Parent")
        child_id = store.add_todo("Child", parent_id=parent_id)
        store.delete_todo(child_id)
        todos = store.get_todos(include_done=True)
        assert len(todos) == 1
        assert todos[0]["id"] == parent_id

    def test_delete_nonexistent_is_noop(self, store: ActivityStore):
        """Deleting a non-existent ID doesn't raise."""
        store.delete_todo(9999)  # Should not raise


class TestMoveTodo:
    """Tests for move_todo()."""

    def test_move_child_to_different_parent(self, store: ActivityStore):
        """Move a Low_Level_Task from one High_Level_Task to another."""
        parent1 = store.add_todo("Bucket A")
        parent2 = store.add_todo("Bucket B")
        child_id = store.add_todo("Task", parent_id=parent1)
        store.move_todo(child_id, parent2)
        todos = store.get_todos(include_done=True)
        child = next(t for t in todos if t["id"] == child_id)
        assert child["parent_id"] == parent2

    def test_move_to_none_makes_top_level(self, store: ActivityStore):
        """Moving with parent_id=None promotes to High_Level_Task."""
        parent_id = store.add_todo("Bucket")
        child_id = store.add_todo("Task", parent_id=parent_id)
        store.move_todo(child_id, None)
        todos = store.get_todos(include_done=True)
        child = next(t for t in todos if t["id"] == child_id)
        assert child["parent_id"] is None


class TestMergeBuckets:
    """Tests for merge_buckets()."""

    def test_merge_moves_children_and_deletes_source(self, store: ActivityStore):
        """Merging moves all children from source to target, then deletes source."""
        source = store.add_todo("Source Bucket")
        target = store.add_todo("Target Bucket")
        c1 = store.add_todo("Child 1", parent_id=source)
        c2 = store.add_todo("Child 2", parent_id=source)
        store.merge_buckets(source, target)
        todos = store.get_todos(include_done=True)
        # Source should be gone
        ids = [t["id"] for t in todos]
        assert source not in ids
        assert target in ids
        assert c1 in ids
        assert c2 in ids
        # Children should now belong to target
        for t in todos:
            if t["id"] in (c1, c2):
                assert t["parent_id"] == target

    def test_merge_empty_source(self, store: ActivityStore):
        """Merging a source with no children just deletes the source."""
        source = store.add_todo("Empty Source")
        target = store.add_todo("Target")
        store.merge_buckets(source, target)
        todos = store.get_todos(include_done=True)
        ids = [t["id"] for t in todos]
        assert source not in ids
        assert target in ids

    def test_merge_preserves_target_children(self, store: ActivityStore):
        """Existing children of target are preserved after merge."""
        source = store.add_todo("Source")
        target = store.add_todo("Target")
        existing = store.add_todo("Existing", parent_id=target)
        new_child = store.add_todo("New", parent_id=source)
        store.merge_buckets(source, target)
        todos = store.get_todos(include_done=True)
        ids = [t["id"] for t in todos]
        assert existing in ids
        assert new_child in ids
        for t in todos:
            if t["id"] in (existing, new_child):
                assert t["parent_id"] == target


class TestClearTodos:
    """Tests for clear_all_todos() and clear_auto_todos()."""

    def test_clear_all_removes_everything(self, store: ActivityStore):
        """clear_all_todos() removes all tasks."""
        store.add_todo("Manual")
        store.add_todo("Auto", auto=True)
        store.clear_all_todos()
        assert store.get_todos(include_done=True) == []

    def test_clear_auto_only_removes_auto(self, store: ActivityStore):
        """clear_auto_todos() removes only auto-generated tasks."""
        manual_id = store.add_todo("Manual")
        store.add_todo("Auto", auto=True)
        store.clear_auto_todos()
        todos = store.get_todos(include_done=True)
        assert len(todos) == 1
        assert todos[0]["id"] == manual_id

    def test_clear_auto_preserves_manual_children(self, store: ActivityStore):
        """clear_auto_todos() doesn't affect manual tasks even if they're children."""
        parent = store.add_todo("Parent")
        manual_child = store.add_todo("Manual Child", parent_id=parent)
        auto_child = store.add_todo("Auto Child", auto=True, parent_id=parent)
        store.clear_auto_todos()
        todos = store.get_todos(include_done=True)
        ids = [t["id"] for t in todos]
        assert parent in ids
        assert manual_child in ids
        assert auto_child not in ids

    def test_clear_all_on_empty_store(self, store: ActivityStore):
        """clear_all_todos() on empty store is a no-op."""
        store.clear_all_todos()  # Should not raise
        assert store.get_todos(include_done=True) == []

    def test_clear_auto_on_empty_store(self, store: ActivityStore):
        """clear_auto_todos() on empty store is a no-op."""
        store.clear_auto_todos()  # Should not raise
        assert store.get_todos(include_done=True) == []


# ------------------------------------------------------------------
# get_activities_by_task / get_activity_summary_by_task
# ------------------------------------------------------------------


class TestGetActivitiesByTask:
    """Tests for get_activities_by_task()."""

    def test_returns_activities_for_task(self, store: ActivityStore):
        """Activities matching task_id and time range are returned."""
        parent = store.add_todo("Tickets")
        task = store.add_todo("auth bug", parent_id=parent)
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 10, 0),
            active_task_id=task,
            activity_summary="researched auth bug",
        ))
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 11, 0),
            active_task_id=task,
            activity_summary="fixed auth bug",
        ))
        results = store.get_activities_by_task(
            task, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert len(results) == 2
        assert all(r.active_task_id == task for r in results)

    def test_excludes_other_tasks(self, store: ActivityStore):
        """Activities for a different task_id are not returned."""
        parent = store.add_todo("Work")
        task_a = store.add_todo("task A", parent_id=parent)
        task_b = store.add_todo("task B", parent_id=parent)
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 10, 0), active_task_id=task_a,
        ))
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 11, 0), active_task_id=task_b,
        ))
        results = store.get_activities_by_task(
            task_a, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert len(results) == 1
        assert results[0].active_task_id == task_a

    def test_filters_by_time_range(self, store: ActivityStore):
        """Only activities within [start, end) are returned."""
        parent = store.add_todo("Work")
        task = store.add_todo("item", parent_id=parent)
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 14, 23, 59), active_task_id=task,
        ))
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 12, 0), active_task_id=task,
        ))
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 16, 0, 0), active_task_id=task,
        ))
        results = store.get_activities_by_task(
            task, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert len(results) == 1
        assert results[0].timestamp == datetime(2025, 1, 15, 12, 0)

    def test_returns_empty_for_no_matches(self, store: ActivityStore):
        results = store.get_activities_by_task(
            999, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert results == []

    def test_ordered_by_timestamp(self, store: ActivityStore):
        parent = store.add_todo("Work")
        task = store.add_todo("item", parent_id=parent)
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 14, 0), active_task_id=task,
        ))
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 9, 0), active_task_id=task,
        ))
        results = store.get_activities_by_task(
            task, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert results[0].timestamp < results[1].timestamp


class TestGetActivitySummaryByTask:
    """Tests for get_activity_summary_by_task()."""

    def test_groups_by_app_and_summary(self, store: ActivityStore):
        """Entries with same app_name + activity_summary are aggregated."""
        parent = store.add_todo("Work")
        task = store.add_todo("item", parent_id=parent)
        for _ in range(3):
            store.save_activity(_make_activity(
                timestamp=datetime(2025, 1, 15, 10, 0),
                app_name="Chrome",
                activity_summary="researched tickets",
                active_task_id=task,
            ))
        for _ in range(2):
            store.save_activity(_make_activity(
                timestamp=datetime(2025, 1, 15, 11, 0),
                app_name="VS Code",
                activity_summary="edited models.py",
                active_task_id=task,
            ))
        results = store.get_activity_summary_by_task(
            task, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert len(results) == 2
        # Ordered by count DESC
        assert results[0]["app_name"] == "Chrome"
        assert results[0]["count"] == 3
        assert results[1]["app_name"] == "VS Code"
        assert results[1]["count"] == 2

    def test_time_seconds_uses_poll_interval(self, store: ActivityStore):
        """time_seconds = count * poll_interval."""
        parent = store.add_todo("Work")
        task = store.add_todo("item", parent_id=parent)
        for _ in range(4):
            store.save_activity(_make_activity(
                timestamp=datetime(2025, 1, 15, 10, 0),
                app_name="Slack",
                activity_summary="chatting",
                active_task_id=task,
            ))
        results = store.get_activity_summary_by_task(
            task, datetime(2025, 1, 15), datetime(2025, 1, 16),
            poll_interval=10,
        )
        assert results[0]["time_seconds"] == 40  # 4 * 10

    def test_includes_first_and_last_seen(self, store: ActivityStore):
        parent = store.add_todo("Work")
        task = store.add_todo("item", parent_id=parent)
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 9, 0),
            app_name="Chrome", activity_summary="browsing", active_task_id=task,
        ))
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 15, 0),
            app_name="Chrome", activity_summary="browsing", active_task_id=task,
        ))
        results = store.get_activity_summary_by_task(
            task, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert results[0]["first_seen"] == datetime(2025, 1, 15, 9, 0).isoformat()
        assert results[0]["last_seen"] == datetime(2025, 1, 15, 15, 0).isoformat()

    def test_includes_category_fields(self, store: ActivityStore):
        parent = store.add_todo("Work")
        task = store.add_todo("item", parent_id=parent)
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 10, 0),
            app_name="VS Code", activity_summary="coding",
            category="Development", sub_category="Python",
            active_task_id=task,
        ))
        results = store.get_activity_summary_by_task(
            task, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert results[0]["category"] == "Development"
        assert results[0]["sub_category"] == "Python"

    def test_returns_empty_for_no_matches(self, store: ActivityStore):
        results = store.get_activity_summary_by_task(
            999, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert results == []

    def test_filters_by_time_range(self, store: ActivityStore):
        parent = store.add_todo("Work")
        task = store.add_todo("item", parent_id=parent)
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 14, 23, 0),
            app_name="Chrome", activity_summary="browsing", active_task_id=task,
        ))
        store.save_activity(_make_activity(
            timestamp=datetime(2025, 1, 15, 10, 0),
            app_name="Chrome", activity_summary="browsing", active_task_id=task,
        ))
        results = store.get_activity_summary_by_task(
            task, datetime(2025, 1, 15), datetime(2025, 1, 16),
        )
        assert len(results) == 1
        assert results[0]["count"] == 1
