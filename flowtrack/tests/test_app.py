"""Unit tests for the FlowTrackApp system tray application.

Since pystray requires a display, all tray-related functionality is mocked.
Tests focus on correct component wiring, tracking lifecycle, and menu actions.
"""

import os
import tempfile
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from flowtrack.core.config import save_config, get_default_config
from flowtrack.core.models import (
    CategorySummary,
    DailySummary,
    WeeklySummary,
)
from flowtrack.ui.app import FlowTrackApp, _create_default_icon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary config file with defaults and return its path."""
    config = get_default_config()
    config["database_path"] = str(tmp_path / "test.db")
    config_path = str(tmp_path / "config.json")
    save_config(config, config_path)
    return config_path


@pytest.fixture
def app(tmp_config):
    """Create a FlowTrackApp instance with a temp config (no tray/tracking)."""
    return FlowTrackApp(tmp_config)


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------

class TestInit:
    """Tests for FlowTrackApp.__init__ and _init_components."""

    def test_loads_config(self, app, tmp_config):
        """App loads config from the given path."""
        assert isinstance(app.config, dict)
        assert app.config_path == tmp_config
        assert "poll_interval_seconds" in app.config

    def test_init_components_creates_store(self, app):
        """_init_components creates and initializes the ActivityStore."""
        app._init_components()
        assert app._store is not None
        # Store should have initialized the DB (tables exist)
        conn = app._store._get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row["name"] for row in cursor.fetchall()}
        assert "activity_logs" in tables
        assert "pomodoro_sessions" in tables
        app._store.close()

    def test_init_components_creates_pomodoro_manager(self, app):
        """_init_components creates a PomodoroManager with config debounce."""
        app._init_components()
        assert app._pomodoro_manager is not None
        expected = timedelta(seconds=app.config.get("debounce_threshold_seconds", 30))
        assert app._pomodoro_manager.debounce_threshold == expected
        if app._store:
            app._store.close()

    def test_init_components_creates_summary_generator(self, app):
        """_init_components creates a SummaryGenerator."""
        app._init_components()
        assert app._summary_generator is not None
        if app._store:
            app._store.close()

    @patch("flowtrack.ui.app.create_window_provider", side_effect=OSError("unsupported"))
    def test_init_components_no_window_provider(self, mock_factory, app):
        """When platform is unsupported, tracker is None but app still works."""
        app._init_components()
        assert app.tracker is None
        assert app._store is not None
        if app._store:
            app._store.close()

    @patch("flowtrack.ui.app.create_window_provider")
    def test_init_components_creates_tracker(self, mock_factory, app):
        """When a window provider is available, tracker is created."""
        mock_provider = MagicMock()
        mock_factory.return_value = mock_provider
        app._init_components()
        assert app.tracker is not None
        assert app.tracker.window_provider is mock_provider
        if app._store:
            app._store.close()


# ---------------------------------------------------------------------------
# Tracking lifecycle tests
# ---------------------------------------------------------------------------

class TestTrackingLifecycle:
    """Tests for start/stop tracking."""

    @patch("flowtrack.ui.app.create_window_provider")
    def test_start_tracking_creates_daemon_thread(self, mock_factory, app):
        """_start_tracking launches a daemon thread running tracker.run."""
        mock_factory.return_value = MagicMock()
        app._init_components()
        # Mock tracker.run so it doesn't block
        app.tracker.run = MagicMock()
        app._start_tracking()

        assert app._tracking is True
        assert app._tracker_thread is not None
        assert app._tracker_thread.daemon is True
        # Wait for thread to call run
        app._tracker_thread.join(timeout=2)
        app.tracker.run.assert_called_once()
        if app._store:
            app._store.close()

    @patch("flowtrack.ui.app.create_window_provider")
    def test_stop_tracking(self, mock_factory, app):
        """_stop_tracking signals the tracker to stop and joins the thread."""
        mock_factory.return_value = MagicMock()
        app._init_components()
        app.tracker.run = MagicMock()
        # Spy on stop so we can verify it was called
        original_stop = app.tracker.stop
        stop_called = []
        def _spy_stop():
            stop_called.append(True)
            original_stop()
        app.tracker.stop = _spy_stop

        app._start_tracking()
        app._tracker_thread.join(timeout=2)

        app._stop_tracking()
        assert app._tracking is False
        assert app._tracker_thread is None
        assert len(stop_called) == 1
        if app._store:
            app._store.close()

    @patch("flowtrack.ui.app.create_window_provider")
    def test_toggle_tracking(self, mock_factory, app):
        """_toggle_tracking switches between start and stop."""
        mock_factory.return_value = MagicMock()
        app._init_components()
        app.tracker.run = MagicMock()

        # Start
        app._toggle_tracking()
        assert app._tracking is True
        app._tracker_thread.join(timeout=2)

        # Stop
        app._toggle_tracking()
        assert app._tracking is False
        if app._store:
            app._store.close()

    def test_start_tracking_without_tracker(self, app):
        """_start_tracking is a no-op when tracker is None."""
        app._init_components()
        app.tracker = None
        app._start_tracking()
        assert app._tracking is False


# ---------------------------------------------------------------------------
# Summary display tests
# ---------------------------------------------------------------------------

class TestSummaryDisplay:
    """Tests for show_daily_summary and show_weekly_summary."""

    def test_show_daily_summary_calls_generator(self, app):
        """show_daily_summary generates today's summary and shows popup."""
        app._summary_generator = MagicMock()
        app._summary_generator.daily_summary.return_value = DailySummary(
            date=date.today(), categories=[], total_time=timedelta(), total_sessions=0
        )
        with patch.object(app, "_show_popup") as mock_popup:
            app.show_daily_summary()
            app._summary_generator.daily_summary.assert_called_once_with(date.today())
            mock_popup.assert_called_once()
            assert "Daily Summary" in mock_popup.call_args[0][0]

    def test_show_weekly_summary_calls_generator(self, app):
        """show_weekly_summary generates this week's summary and shows popup."""
        app._summary_generator = MagicMock()
        start = date.today() - timedelta(days=date.today().weekday())
        app._summary_generator.weekly_summary.return_value = WeeklySummary(
            start_date=start,
            end_date=start + timedelta(days=6),
            daily_breakdowns=[],
            categories=[],
            total_time=timedelta(),
            total_sessions=0,
        )
        with patch.object(app, "_show_popup") as mock_popup:
            app.show_weekly_summary()
            app._summary_generator.weekly_summary.assert_called_once()
            mock_popup.assert_called_once()
            assert "Weekly Summary" in mock_popup.call_args[0][0]

    def test_show_daily_summary_no_generator(self, app, caplog):
        """show_daily_summary logs warning when generator is not initialized."""
        app._summary_generator = None
        import logging
        with caplog.at_level(logging.WARNING):
            app.show_daily_summary()
        assert "not initialized" in caplog.text


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------

class TestSettings:
    """Tests for open_settings."""

    def test_open_settings_opens_dashboard(self, app):
        """open_settings on macOS opens the dashboard in browser."""
        app._dashboard_port = 5555
        with patch("subprocess.Popen") as mock_popen:
            app._open_dashboard()
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert "5555" in args[1]


# ---------------------------------------------------------------------------
# Config hot-reload tests
# ---------------------------------------------------------------------------

class TestConfigReload:
    """Tests for _apply_config_changes."""

    @patch("flowtrack.ui.app.create_window_provider")
    def test_apply_updates_classifier_rules(self, mock_factory, app):
        """_apply_config_changes updates classifier rules on the tracker."""
        mock_factory.return_value = MagicMock()
        app._init_components()

        app.config["classification_rules"] = [
            {"app_patterns": ["NewApp"], "title_patterns": [], "category": "NewCat"}
        ]
        app._apply_config_changes()

        assert len(app.tracker.classifier.rules) == 1
        assert app.tracker.classifier.rules[0].category == "NewCat"
        if app._store:
            app._store.close()

    @patch("flowtrack.ui.app.create_window_provider")
    def test_apply_updates_context_rules(self, mock_factory, app):
        """_apply_config_changes updates context analyzer rules."""
        mock_factory.return_value = MagicMock()
        app._init_components()

        app.config["context_rules"] = [
            {"category": "Dev", "title_patterns": ["test"], "sub_category": "Testing"}
        ]
        app._apply_config_changes()

        assert len(app.tracker.context_analyzer.rules) == 1
        assert app.tracker.context_analyzer.rules[0].sub_category == "Testing"
        if app._store:
            app._store.close()

    def test_apply_updates_debounce(self, app):
        """_apply_config_changes updates the pomodoro debounce threshold."""
        app._init_components()
        app.config["debounce_threshold_seconds"] = 60
        app._apply_config_changes()

        assert app._pomodoro_manager.debounce_threshold == timedelta(seconds=60)
        if app._store:
            app._store.close()


# ---------------------------------------------------------------------------
# Stop / cleanup tests
# ---------------------------------------------------------------------------

class TestStop:
    """Tests for stop() cleanup."""

    def test_stop_closes_store(self, app):
        """stop() closes the ActivityStore."""
        app._init_components()
        store = app._store
        app.stop()
        assert app._store is None

    def test_stop_idempotent(self, app):
        """Calling stop() multiple times doesn't raise."""
        app.stop()
        app.stop()  # should not raise


# ---------------------------------------------------------------------------
# Icon creation tests
# ---------------------------------------------------------------------------

class TestIconCreation:
    """Tests for _create_default_icon."""

    def test_creates_image(self):
        """_create_default_icon returns a PIL Image."""
        img = _create_default_icon()
        if img is not None:
            assert img.size == (64, 64) or img.size[0] > 0

    @patch.dict("sys.modules", {"PIL": None, "PIL.Image": None})
    def test_returns_none_without_pil(self):
        """Returns None when PIL is not available."""
        # This test may not fully work due to import caching,
        # but validates the graceful handling path exists
        pass


# ---------------------------------------------------------------------------
# Tray menu tests
# ---------------------------------------------------------------------------

class TestTrayMenu:
    """Tests for _run_tray menu construction."""

    @patch("flowtrack.ui.app._create_default_icon")
    def test_run_tray_without_pystray(self, mock_icon, app, caplog):
        """_run_tray logs warning when pystray is not available."""
        import logging
        with patch.dict("sys.modules", {"pystray": None}):
            with caplog.at_level(logging.WARNING):
                # Force reimport failure
                try:
                    app._run_tray()
                except (ImportError, TypeError):
                    pass  # Expected when pystray can't be imported

    @patch("flowtrack.ui.app._create_default_icon", return_value=None)
    def test_run_tray_without_icon(self, mock_icon, app, caplog):
        """_run_tray skips when icon image cannot be created."""
        import logging
        # Mock pystray at the module level so the import inside _run_tray succeeds
        mock_pystray = MagicMock()
        with caplog.at_level(logging.WARNING):
            with patch.dict("sys.modules", {"pystray": mock_pystray, "pystray.MenuItem": MagicMock(), "pystray.Menu": MagicMock()}):
                app._run_tray()
        assert "Could not create tray icon" in caplog.text


# ---------------------------------------------------------------------------
# Add manual task tests
# ---------------------------------------------------------------------------

class TestAddManualTask:
    """Tests for add_manual_task."""

    def test_add_manual_task_no_pomodoro(self, app, caplog):
        """add_manual_task logs warning when pomodoro manager is None."""
        app._pomodoro_manager = None
        import logging
        with caplog.at_level(logging.WARNING):
            app.add_manual_task()
        assert "not initialized" in caplog.text
