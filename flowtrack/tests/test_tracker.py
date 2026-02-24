"""Unit tests for the Tracker orchestrator."""

import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from flowtrack.core.classifier import Classifier
from flowtrack.core.context_analyzer import ContextAnalyzer
from flowtrack.core.models import (
    ActivityRecord,
    ContextResult,
    PomodoroSession,
    SessionStatus,
    WindowInfo,
)
from flowtrack.core.pomodoro import PomodoroManager
from flowtrack.core.tracker import Tracker
from flowtrack.persistence.store import ActivityStore
from flowtrack.platform.base import WindowProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracker(
    window_info=None,
    is_idle=False,
    category="Development",
    context_result=None,
    on_activity_events=None,
    tick_events=None,
    active_session=None,
    get_window_side_effect=None,
    poll_interval=5,
):
    """Build a Tracker wired to mocks with sensible defaults."""
    provider = MagicMock(spec=WindowProvider)
    if get_window_side_effect is not None:
        provider.get_active_window.side_effect = get_window_side_effect
    else:
        provider.get_active_window.return_value = window_info
    provider.is_user_idle.return_value = is_idle

    classifier = MagicMock(spec=Classifier)
    classifier.classify.return_value = category

    if context_result is None:
        context_result = ContextResult(
            category=category, sub_category=category, context_label=category
        )
    analyzer = MagicMock(spec=ContextAnalyzer)
    analyzer.analyze.return_value = context_result

    pomodoro = MagicMock(spec=PomodoroManager)
    pomodoro.on_activity.return_value = on_activity_events or []
    pomodoro.tick.return_value = tick_events or []
    pomodoro.active_session = active_session

    store = MagicMock(spec=ActivityStore)
    store.save_activity.return_value = 1

    tracker = Tracker(
        window_provider=provider,
        classifier=classifier,
        context_analyzer=analyzer,
        pomodoro_manager=pomodoro,
        store=store,
        poll_interval=poll_interval,
    )
    return tracker, provider, classifier, analyzer, pomodoro, store


# ---------------------------------------------------------------------------
# poll_once tests
# ---------------------------------------------------------------------------

class TestPollOnce:
    """Tests for Tracker.poll_once()."""

    def test_full_pipeline(self):
        """poll_once executes the full data flow: window → classify → context → pomodoro → persist."""
        win = WindowInfo(app_name="VS Code", window_title="tracker.py - CarrotSummary")
        ctx = ContextResult(
            category="Development",
            sub_category="Code Editing",
            context_label="Code Editing: tracker.py",
        )
        session = PomodoroSession(
            id="sess-1",
            category="Development",
            sub_category="Code Editing",
            start_time=datetime(2025, 1, 1, 9, 0),
            elapsed=timedelta(minutes=5),
            status=SessionStatus.ACTIVE,
            completed_count=0,
        )
        now = datetime(2025, 1, 1, 9, 5)

        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win,
            category="Development",
            context_result=ctx,
            active_session=session,
        )

        tracker.poll_once(now)

        provider.get_active_window.assert_called_once()
        classifier.classify.assert_called_once_with("VS Code", "tracker.py - CarrotSummary")
        analyzer.analyze.assert_called_once_with("VS Code", "tracker.py - CarrotSummary", "Development")
        pomodoro.on_activity.assert_called_once_with("Development", "Code Editing", now)
        pomodoro.tick.assert_called_once_with(now)

        # Activity record saved
        store.save_activity.assert_called_once()
        record: ActivityRecord = store.save_activity.call_args[0][0]
        assert record.timestamp == now
        assert record.app_name == "VS Code"
        assert record.window_title == "tracker.py - CarrotSummary"
        assert record.category == "Development"
        assert record.sub_category == "Code Editing"
        assert record.session_id == "sess-1"

        # Session persisted
        store.save_session.assert_called_once_with(session)

    def test_no_active_window_skips(self):
        """poll_once does nothing when get_active_window returns None."""
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=None
        )

        tracker.poll_once(datetime.now())

        classifier.classify.assert_not_called()
        store.save_activity.assert_not_called()

    def test_window_api_error_logs_and_continues(self, caplog):
        """poll_once catches exceptions from get_active_window and continues (Req 1.3)."""
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            get_window_side_effect=OSError("API unavailable"),
        )

        with caplog.at_level(logging.ERROR):
            tracker.poll_once(datetime.now())

        assert "Failed to get active window" in caplog.text
        classifier.classify.assert_not_called()
        store.save_activity.assert_not_called()

    def test_no_session_saves_activity_without_session_id(self):
        """When pomodoro has no active session, activity is saved with session_id=None."""
        win = WindowInfo(app_name="Notepad", window_title="Untitled")
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win,
            category="Other",
            active_session=None,
        )

        tracker.poll_once(datetime(2025, 1, 1, 10, 0))

        store.save_activity.assert_called_once()
        record: ActivityRecord = store.save_activity.call_args[0][0]
        assert record.session_id is None
        store.save_session.assert_not_called()

    def test_activity_record_has_zero_id(self):
        """The ActivityRecord passed to save_activity has id=0 (auto-increment)."""
        win = WindowInfo(app_name="Chrome", window_title="Google")
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win,
            category="Research & Browsing",
            active_session=None,
        )

        tracker.poll_once(datetime(2025, 6, 1, 12, 0))

        record: ActivityRecord = store.save_activity.call_args[0][0]
        assert record.id == 0

    def test_active_task_id_propagated_to_record(self):
        """When current_active_task_id is set, the ActivityRecord carries that ID (Req 1.2, 14.7)."""
        win = WindowInfo(app_name="Chrome", window_title="Tickets Portal - Auth Issue")
        ctx = ContextResult(
            category="Research & Browsing",
            sub_category="Tickets",
            context_label="Tickets: Auth Issue",
            activity_summary="researched authentication issue",
        )
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win,
            category="Research & Browsing",
            context_result=ctx,
            active_session=None,
        )
        tracker.current_active_task_id = 42

        tracker.poll_once(datetime(2025, 6, 1, 14, 0))

        record: ActivityRecord = store.save_activity.call_args[0][0]
        assert record.active_task_id == 42

    def test_active_task_id_none_when_no_task_selected(self):
        """When no current_active_task_id is set, the ActivityRecord has active_task_id=None (Req 14.4)."""
        win = WindowInfo(app_name="Notepad", window_title="Untitled")
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win,
            category="Other",
            active_session=None,
        )
        # current_active_task_id defaults to None

        tracker.poll_once(datetime(2025, 6, 1, 14, 0))

        record: ActivityRecord = store.save_activity.call_args[0][0]
        assert record.active_task_id is None

    def test_active_task_id_propagated_to_pomodoro_manager(self):
        """Tracker sets pomodoro_manager.active_task_id before on_activity (Req 3.5)."""
        win = WindowInfo(app_name="Chrome", window_title="Tickets Portal")
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win,
            category="Research & Browsing",
            active_session=None,
        )
        tracker.current_active_task_id = 99

        # Track what active_task_id was set to before on_activity was called
        captured_task_id = []

        def capture_on_activity(*args, **kwargs):
            captured_task_id.append(pomodoro.active_task_id)
            return []

        pomodoro.on_activity.side_effect = capture_on_activity

        tracker.poll_once(datetime(2025, 6, 1, 14, 0))

        assert captured_task_id == [99]

    def test_activity_summary_propagated_from_context(self):
        """The activity_summary from ContextResult is set on the ActivityRecord (Req 14.2, 14.3)."""
        win = WindowInfo(app_name="VS Code", window_title="auth.py - MyProject")
        ctx = ContextResult(
            category="Development",
            sub_category="Code Editing",
            context_label="Code Editing: auth.py",
            activity_summary="edited auth.py in MyProject",
        )
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win,
            category="Development",
            context_result=ctx,
            active_session=None,
        )
        tracker.current_active_task_id = 7

        tracker.poll_once(datetime(2025, 6, 1, 15, 0))

        record: ActivityRecord = store.save_activity.call_args[0][0]
        assert record.activity_summary == "edited auth.py in MyProject"
        assert record.active_task_id == 7

    def test_activity_summary_empty_when_context_has_none(self):
        """When ContextResult has no activity_summary, the record gets an empty string."""
        win = WindowInfo(app_name="Finder", window_title="Documents")
        ctx = ContextResult(
            category="Other",
            sub_category="Other",
            context_label="Other",
            # activity_summary defaults to ""
        )
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win,
            category="Other",
            context_result=ctx,
            active_session=None,
        )

        tracker.poll_once(datetime(2025, 6, 1, 16, 0))

        record: ActivityRecord = store.save_activity.call_args[0][0]
        assert record.activity_summary == ""



# ---------------------------------------------------------------------------
# run / stop tests
# ---------------------------------------------------------------------------

class TestRunLoop:
    """Tests for Tracker.run() and stop()."""

    def test_stop_terminates_loop(self):
        """Calling stop() causes run() to exit."""
        win = WindowInfo(app_name="App", window_title="Title")
        tracker, provider, *_ = _make_tracker(window_info=win, poll_interval=0)

        call_count = 0

        def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                tracker.stop()

        with patch("flowtrack.core.tracker.time.sleep", side_effect=fake_sleep):
            tracker.run()

        assert not tracker._running
        assert call_count >= 3

    def test_idle_skips_poll(self):
        """When user is idle, poll_once is not called (Req 1.4)."""
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            is_idle=True, poll_interval=0
        )

        call_count = 0

        def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                tracker.stop()

        with patch("flowtrack.core.tracker.time.sleep", side_effect=fake_sleep):
            tracker.run()

        # Classifier should never be called because idle skips the poll
        classifier.classify.assert_not_called()

    def test_idle_check_error_assumes_not_idle(self, caplog):
        """If is_user_idle raises, we assume not idle and poll anyway (Req 1.3)."""
        win = WindowInfo(app_name="App", window_title="Title")
        tracker, provider, classifier, analyzer, pomodoro, store = _make_tracker(
            window_info=win, poll_interval=0
        )
        provider.is_user_idle.side_effect = RuntimeError("idle check failed")

        call_count = 0

        def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                tracker.stop()

        with caplog.at_level(logging.ERROR):
            with patch("flowtrack.core.tracker.time.sleep", side_effect=fake_sleep):
                tracker.run()

        assert "Failed to check idle state" in caplog.text
        # poll_once should still have been called
        classifier.classify.assert_called()
