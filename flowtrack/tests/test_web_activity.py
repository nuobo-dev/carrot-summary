"""Tests for the /api/activity/by-task web endpoint (Task 19.1)."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from flowtrack.core.models import ActivityRecord
from flowtrack.persistence.store import ActivityStore
from flowtrack.ui.web import create_flask_app, _aggregate_activities
import flowtrack.ui.web as web_module


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = ActivityStore(str(db))
    s.init_db()
    return s


@pytest.fixture
def app_ref(store):
    """Minimal mock of the app object that the web module expects."""
    ref = MagicMock()
    ref._store = store
    ref._tracking = True
    ref.tracker = MagicMock()
    ref.tracker.current_active_task_id = None
    ref._pomodoro_manager = None
    ref._summary_generator = None
    ref.config = {"poll_interval_seconds": 5}
    return ref


@pytest.fixture
def client(app_ref):
    old = web_module._app_ref
    web_module._app_ref = app_ref
    flask_app = create_flask_app()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
    web_module._app_ref = old


def _make_activity(store, ts, app_name, title, category, task_id=None, summary=""):
    rec = ActivityRecord(
        id=0, timestamp=ts, app_name=app_name, window_title=title,
        category=category, sub_category="", session_id=None,
        active_task_id=task_id, activity_summary=summary,
    )
    return store.save_activity(rec)


class TestActivityByTaskEndpoint:
    """Tests for GET /api/activity/by-task."""

    def test_empty_day_returns_empty(self, client):
        resp = client.get("/api/activity/by-task?date=2025-01-15")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["date"] == "2025-01-15"
        assert data["tasks"] == []
        assert data["unassigned"]["total_seconds"] == 0
        assert data["unassigned"]["entries"] == []

    def test_unassigned_activities(self, client, store):
        """Activities with no active_task_id go under 'Unassigned'."""
        ts = datetime(2025, 1, 15, 10, 0, 0)
        _make_activity(store, ts, "Chrome", "Google", "Research", task_id=None, summary="browsing")
        _make_activity(store, ts + timedelta(seconds=5), "Chrome", "Google", "Research", task_id=None, summary="browsing")

        resp = client.get("/api/activity/by-task?date=2025-01-15")
        data = resp.get_json()
        assert data["unassigned"]["total_seconds"] == 10  # 2 polls * 5s
        assert len(data["unassigned"]["entries"]) == 1
        assert data["unassigned"]["entries"][0]["app_name"] == "Chrome"
        assert data["unassigned"]["entries"][0]["summary"] == "browsing"

    def test_activities_organized_by_task_hierarchy(self, client, store):
        """Activities are grouped under High_Level → Low_Level → entries."""
        # Create task hierarchy
        parent_id = store.add_todo("Tickets", "")
        child_id = store.add_todo("auth issue", "", parent_id=parent_id)

        ts = datetime(2025, 1, 15, 9, 0, 0)
        for i in range(3):
            _make_activity(store, ts + timedelta(seconds=i * 5), "Browser", "Tickets Portal",
                           "Research", task_id=child_id, summary="researched auth issue")

        resp = client.get("/api/activity/by-task?date=2025-01-15")
        data = resp.get_json()

        assert len(data["tasks"]) == 1
        parent_task = data["tasks"][0]
        assert parent_task["title"] == "Tickets"
        assert parent_task["total_seconds"] == 15  # 3 * 5s

        assert len(parent_task["children"]) == 1
        child_task = parent_task["children"][0]
        assert child_task["title"] == "auth issue"
        assert child_task["total_seconds"] == 15

        assert len(child_task["entries"]) == 1
        entry = child_task["entries"][0]
        assert entry["app_name"] == "Browser"
        assert entry["summary"] == "researched auth issue"
        assert entry["time_seconds"] == 15

    def test_multiple_tasks_and_unassigned(self, client, store):
        """Multiple high-level tasks plus unassigned activities."""
        p1 = store.add_todo("Design Work", "")
        c1 = store.add_todo("mockups", "", parent_id=p1)
        p2 = store.add_todo("Code Reviews", "")
        c2 = store.add_todo("PR #42", "", parent_id=p2)

        ts = datetime(2025, 1, 15, 10, 0, 0)
        _make_activity(store, ts, "Figma", "Design", "Creative", task_id=c1, summary="edited mockups")
        _make_activity(store, ts + timedelta(seconds=5), "GitHub", "PR", "Development", task_id=c2, summary="reviewed PR")
        _make_activity(store, ts + timedelta(seconds=10), "Slack", "Chat", "Communication", task_id=None, summary="chatting")

        resp = client.get("/api/activity/by-task?date=2025-01-15")
        data = resp.get_json()

        assert len(data["tasks"]) == 2
        titles = {t["title"] for t in data["tasks"]}
        assert titles == {"Design Work", "Code Reviews"}
        assert data["unassigned"]["total_seconds"] == 5

    def test_entries_include_timestamp_range(self, client, store):
        """Each aggregated entry includes timestamp_start and timestamp_end."""
        parent_id = store.add_todo("Work", "")
        child_id = store.add_todo("task1", "", parent_id=parent_id)

        ts1 = datetime(2025, 1, 15, 9, 0, 0)
        ts2 = datetime(2025, 1, 15, 9, 5, 0)
        _make_activity(store, ts1, "VSCode", "main.py", "Development", task_id=child_id, summary="coding")
        _make_activity(store, ts2, "VSCode", "main.py", "Development", task_id=child_id, summary="coding")

        resp = client.get("/api/activity/by-task?date=2025-01-15")
        data = resp.get_json()
        entry = data["tasks"][0]["children"][0]["entries"][0]
        assert "timestamp_start" in entry
        assert "timestamp_end" in entry
        assert entry["timestamp_start"] == ts1.isoformat()
        assert entry["timestamp_end"] == ts2.isoformat()

    def test_aggregation_groups_by_app_and_summary(self, client, store):
        """Different app+summary combos produce separate entries."""
        parent_id = store.add_todo("Work", "")
        child_id = store.add_todo("task1", "", parent_id=parent_id)

        ts = datetime(2025, 1, 15, 10, 0, 0)
        _make_activity(store, ts, "Chrome", "Docs", "Research", task_id=child_id, summary="reading docs")
        _make_activity(store, ts + timedelta(seconds=5), "VSCode", "app.py", "Development", task_id=child_id, summary="coding")

        resp = client.get("/api/activity/by-task?date=2025-01-15")
        data = resp.get_json()
        entries = data["tasks"][0]["children"][0]["entries"]
        assert len(entries) == 2
        apps = {e["app_name"] for e in entries}
        assert apps == {"Chrome", "VSCode"}

    def test_defaults_to_today(self, client, store):
        """When no date param is given, defaults to today."""
        resp = client.get("/api/activity/by-task")
        assert resp.status_code == 200
        from datetime import date
        data = resp.get_json()
        assert data["date"] == str(date.today())


class TestAggregateActivities:
    """Unit tests for the _aggregate_activities helper."""

    def test_empty_list(self):
        assert _aggregate_activities([], 5) == []

    def test_single_activity(self):
        act = ActivityRecord(
            id=1, timestamp=datetime(2025, 1, 15, 10, 0),
            app_name="Chrome", window_title="Google", category="Research",
            sub_category="", session_id=None, activity_summary="browsing",
        )
        result = _aggregate_activities([act], 5)
        assert len(result) == 1
        assert result[0]["app_name"] == "Chrome"
        assert result[0]["summary"] == "browsing"
        assert result[0]["time_seconds"] == 5
        assert "timestamp_start" in result[0]
        assert "timestamp_end" in result[0]

    def test_aggregation_combines_same_key(self):
        ts = datetime(2025, 1, 15, 10, 0)
        acts = [
            ActivityRecord(id=i, timestamp=ts + timedelta(seconds=i * 5),
                           app_name="VSCode", window_title="file.py",
                           category="Dev", sub_category="", session_id=None,
                           activity_summary="coding")
            for i in range(4)
        ]
        result = _aggregate_activities(acts, 5)
        assert len(result) == 1
        assert result[0]["time_seconds"] == 20
        assert result[0]["timestamp_start"] == ts.isoformat()
        assert result[0]["timestamp_end"] == (ts + timedelta(seconds=15)).isoformat()

    def test_sorted_by_time_descending(self):
        ts = datetime(2025, 1, 15, 10, 0)
        acts = [
            ActivityRecord(id=1, timestamp=ts, app_name="A", window_title="",
                           category="X", sub_category="", session_id=None,
                           activity_summary="a"),
            ActivityRecord(id=2, timestamp=ts, app_name="B", window_title="",
                           category="X", sub_category="", session_id=None,
                           activity_summary="b"),
            ActivityRecord(id=3, timestamp=ts + timedelta(seconds=5), app_name="B",
                           window_title="", category="X", sub_category="",
                           session_id=None, activity_summary="b"),
        ]
        result = _aggregate_activities(acts, 5)
        assert result[0]["app_name"] == "B"  # 2 entries = 10s
        assert result[1]["app_name"] == "A"  # 1 entry = 5s

    def test_normalization_combines_case_variants(self):
        """Entries differing only in case should be combined."""
        ts = datetime(2025, 1, 15, 10, 0)
        acts = [
            ActivityRecord(id=1, timestamp=ts, app_name="Chrome", window_title="",
                           category="Research", sub_category="", session_id=None,
                           activity_summary="Browsing Payment history"),
            ActivityRecord(id=2, timestamp=ts + timedelta(seconds=5), app_name="Chrome",
                           window_title="", category="Research", sub_category="",
                           session_id=None, activity_summary="browsing payment history"),
            ActivityRecord(id=3, timestamp=ts + timedelta(seconds=10), app_name="chrome",
                           window_title="", category="Research", sub_category="",
                           session_id=None, activity_summary="Browsing Payment history"),
        ]
        result = _aggregate_activities(acts, 5)
        assert len(result) == 1
        assert result[0]["time_seconds"] == 15  # 3 * 5s

    def test_normalization_combines_whitespace_variants(self):
        """Entries differing only in whitespace should be combined."""
        ts = datetime(2025, 1, 15, 10, 0)
        acts = [
            ActivityRecord(id=1, timestamp=ts, app_name="Chrome", window_title="",
                           category="Research", sub_category="", session_id=None,
                           activity_summary="researched  auth issue"),
            ActivityRecord(id=2, timestamp=ts + timedelta(seconds=5), app_name="Chrome",
                           window_title="", category="Research", sub_category="",
                           session_id=None, activity_summary="researched auth issue"),
        ]
        result = _aggregate_activities(acts, 5)
        assert len(result) == 1
        assert result[0]["time_seconds"] == 10
