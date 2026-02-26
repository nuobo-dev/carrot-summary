"""System tray application for CarrotSummary.

Provides a pystray-based system tray icon with menu items for controlling
tracking, viewing summaries, opening settings, and quitting. The Tracker
runs in a daemon background thread so the tray icon remains responsive.
"""

import logging
import os
import sys
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from flowtrack.core.classifier import Classifier
from flowtrack.core.config import load_config, save_config
from flowtrack.core.context_analyzer import ContextAnalyzer
from flowtrack.core.models import ClassificationRule, ContextRule, SmtpConfig
from flowtrack.core.pomodoro import PomodoroManager
from flowtrack.core.tracker import Tracker
from flowtrack.persistence.store import ActivityStore
from flowtrack.platform.factory import create_window_provider
from flowtrack.reporting.formatter import TextFormatter
from flowtrack.reporting.summary import SummaryGenerator

logger = logging.getLogger(__name__)


def _create_default_icon():
    """Create a simple default icon image using PIL, or load from assets."""
    try:
        from PIL import Image
    except ImportError:
        return None

    # Try loading the bundled icon first
    assets_dir = Path(__file__).resolve().parent.parent.parent / "assets"
    icon_path = assets_dir / "icon.png"
    if icon_path.exists():
        try:
            return Image.open(str(icon_path))
        except Exception:
            logger.debug("Could not load icon from %s, creating default", icon_path)

    # Fallback: create a simple 64x64 icon
    img = Image.new("RGB", (64, 64), color=(90, 125, 154))
    return img


class CarrotSummaryApp:
    """Main application class that runs CarrotSummary as a system tray app."""

    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self.config = load_config(config_path)
        self.tracker: Optional[Tracker] = None
        self.tray_icon = None
        self._tracker_thread: Optional[threading.Thread] = None
        self._tracking = False
        self._store: Optional[ActivityStore] = None
        self._summary_generator: Optional[SummaryGenerator] = None
        self._pomodoro_manager: Optional[PomodoroManager] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialize all components, start the tracker in a background thread,
        and display the system tray icon."""
        self._init_components()
        self._start_tracking()
        self._start_dashboard()
        self._run_tray()

    def stop(self) -> None:
        """Stop tracking and clean up resources."""
        self._stop_tracking()
        if self._store is not None:
            self._store.close()
            self._store = None
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                logger.debug("Tray icon already stopped")
            self.tray_icon = None

    def show_daily_summary(self) -> None:
        """Display today's summary in a popup window."""
        if self._summary_generator is None:
            logger.warning("Summary generator not initialized")
            return

        try:
            summary = self._summary_generator.daily_summary(date.today())
            text = TextFormatter.format_daily(summary)
            self._show_popup("Daily Summary", text)
        except Exception:
            logger.exception("Failed to generate daily summary")

    def show_weekly_summary(self) -> None:
        """Generate and display the weekly summary."""
        if self._summary_generator is None:
            logger.warning("Summary generator not initialized")
            return

        try:
            start_date = date.today() - timedelta(days=date.today().weekday())
            summary = self._summary_generator.weekly_summary(start_date)
            text = TextFormatter.format_weekly(summary)
            self._show_popup("Weekly Summary", text)
        except Exception:
            logger.exception("Failed to generate weekly summary")

    def open_settings(self) -> None:
        """Open the settings — on macOS use native dialog to reveal config file."""
        if sys.platform == "darwin":
            import subprocess
            config_path = self.config_path
            script = (
                f'display dialog "Settings are stored at:\\n\\n{config_path}\\n\\n'
                f'Would you like to open the config file?" '
                f'with title "CarrotSummary Settings" '
                f'buttons {{"Cancel", "Open Config"}} default button "Open Config"'
            )
            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0 and "Open Config" in result.stdout:
                    subprocess.Popen(["open", "-t", config_path])
            except Exception:
                logger.exception("Failed to open settings")
        else:
            try:
                from flowtrack.ui.settings import SettingsWindow

                def _on_save(updated_config: dict[str, Any]) -> None:
                    self.config = updated_config
                    save_config(updated_config, self.config_path)
                    self._apply_config_changes()
                    logger.info("Settings saved and applied")

                settings = SettingsWindow(self.config, _on_save)
                settings.show()
            except Exception:
                logger.exception("Failed to open settings window")

    def add_manual_task(self) -> None:
        """Prompt user to create a manual Pomodoro task via a simple dialog."""
        if self._pomodoro_manager is None:
            logger.warning("Pomodoro manager not initialized")
            return

        try:
            self._show_manual_task_dialog()
        except Exception:
            logger.exception("Failed to create manual task")
    def set_active_task(self, task_id: int) -> None:
        """Set the Current_Active_Task. Updates tracker and pomodoro manager.

        Sets ``Tracker.current_active_task_id`` so subsequent polls tag
        activities with this task, and updates the active Pomodoro session
        (or starts/switches one) to track against the new task.
        """
        if self.tracker is not None:
            self.tracker.current_active_task_id = task_id
        if self._pomodoro_manager is not None:
            self._pomodoro_manager.active_task_id = task_id
            if self._pomodoro_manager.active_session is not None:
                self._pomodoro_manager.active_session.active_task_id = task_id

    def clear_active_task(self) -> None:
        """Clear the Current_Active_Task. Activities go to 'Unassigned'."""
        if self.tracker is not None:
            self.tracker.current_active_task_id = None
        if self._pomodoro_manager is not None:
            self._pomodoro_manager.active_task_id = None
            if self._pomodoro_manager.active_session is not None:
                self._pomodoro_manager.active_session.active_task_id = None



    # ------------------------------------------------------------------
    # Component initialization
    # ------------------------------------------------------------------

    def _init_components(self) -> None:
        """Wire up all CarrotSummary components from config."""
        config = self.config

        # Database
        db_path = config.get("database_path", "~/.flowtrack/flowtrack.db")
        db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._store = ActivityStore(db_path)
        self._store.init_db()

        # Classifier
        raw_rules = config.get("classification_rules", [])
        rules = [
            ClassificationRule(
                app_patterns=r.get("app_patterns", []),
                title_patterns=r.get("title_patterns", []),
                category=r.get("category", "Other"),
            )
            for r in raw_rules
        ]
        classifier = Classifier(rules)

        # Context Analyzer
        raw_ctx = config.get("context_rules", [])
        ctx_rules = [
            ContextRule(
                category=r.get("category", ""),
                title_patterns=r.get("title_patterns", []),
                sub_category=r.get("sub_category", ""),
            )
            for r in raw_ctx
        ]
        context_analyzer = ContextAnalyzer(ctx_rules)

        # Pomodoro Manager
        debounce = config.get("debounce_threshold_seconds", 30)
        self._pomodoro_manager = PomodoroManager(debounce_seconds=debounce)

        # Summary Generator
        poll_interval = config.get("poll_interval_seconds", 5)
        self._summary_generator = SummaryGenerator(self._store, poll_interval)

        # Window Provider
        try:
            window_provider = create_window_provider()
        except OSError:
            logger.warning("No window provider for this platform; tracking disabled")
            window_provider = None

        # Tracker
        ml_enabled = config.get("ml_screen_analysis", False)
        if window_provider is not None:
            self.tracker = Tracker(
                window_provider=window_provider,
                classifier=classifier,
                context_analyzer=context_analyzer,
                pomodoro_manager=self._pomodoro_manager,
                store=self._store,
                poll_interval=poll_interval,
                ml_screen_analysis=ml_enabled,
            )

    # ------------------------------------------------------------------
    # Tracking control
    # ------------------------------------------------------------------

    def _start_tracking(self) -> None:
        """Start the tracker in a daemon background thread."""
        if self.tracker is None:
            logger.info("No tracker available; skipping background tracking")
            return
        if self._tracking:
            return

        self._tracking = True
        self._tracker_thread = threading.Thread(
            target=self.tracker.run, daemon=True, name="flowtrack-tracker"
        )
        self._tracker_thread.start()
        logger.info("Tracking started in background thread")

    def _stop_tracking(self) -> None:
        """Stop the tracker background thread."""
        if self.tracker is not None:
            self.tracker.stop()
        self._tracking = False
        if self._tracker_thread is not None:
            self._tracker_thread.join(timeout=5)
            self._tracker_thread = None
        logger.info("Tracking stopped")

    def _toggle_tracking(self) -> None:
        """Toggle tracking on/off from the tray menu."""
        if self._tracking:
            self._stop_tracking()
        else:
            self._start_tracking()

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _run_tray(self) -> None:
        """Create and run the pystray system tray icon."""
        try:
            import pystray
            from pystray import MenuItem, Menu
        except ImportError:
            logger.warning(
                "pystray not available; running without system tray. "
                "Install pystray for tray icon support."
            )
            return

        icon_image = _create_default_icon()
        if icon_image is None:
            logger.warning("Could not create tray icon image; skipping tray")
            return

        def _tracking_label(item):
            return "Stop Tracking" if self._tracking else "Start Tracking"

        menu = Menu(
            MenuItem(_tracking_label, lambda: self._toggle_tracking()),
            Menu.SEPARATOR,
            MenuItem("Dashboard", lambda: self._open_dashboard()),
            MenuItem("Daily Summary", lambda: self.show_daily_summary()),
            MenuItem("Weekly Report", lambda: self.show_weekly_summary()),
            Menu.SEPARATOR,
            MenuItem("Add Task", lambda: self.add_manual_task()),
            MenuItem("Settings", lambda: self._open_dashboard()),
            Menu.SEPARATOR,
            MenuItem("Quit", lambda: self._quit()),
        )

        self.tray_icon = pystray.Icon("CarrotSummary", icon_image, "CarrotSummary", menu)
        self.tray_icon.run()

    def _quit(self) -> None:
        """Quit the application cleanly."""
        self.stop()

    # ------------------------------------------------------------------
    # Web dashboard
    # ------------------------------------------------------------------

    def _start_dashboard(self) -> None:
        """Start the web dashboard in a background thread."""
        try:
            from flowtrack.ui.web import start_dashboard
            self._dashboard_port = 5555
            start_dashboard(self, port=self._dashboard_port)
        except Exception:
            logger.exception("Failed to start web dashboard")

    def _open_dashboard(self) -> None:
        """Open the dashboard in the default browser."""
        import subprocess
        try:
            subprocess.Popen(["open", f"http://127.0.0.1:{self._dashboard_port}"])
        except Exception:
            logger.exception("Failed to open dashboard")

    # ------------------------------------------------------------------
    # Config hot-reload
    # ------------------------------------------------------------------

    def _apply_config_changes(self) -> None:
        """Apply updated config to running components without restart."""
        config = self.config

        # Update classifier rules
        if self.tracker is not None:
            raw_rules = config.get("classification_rules", [])
            self.tracker.classifier.rules = [
                ClassificationRule(
                    app_patterns=r.get("app_patterns", []),
                    title_patterns=r.get("title_patterns", []),
                    category=r.get("category", "Other"),
                )
                for r in raw_rules
            ]

            # Update context analyzer rules
            raw_ctx = config.get("context_rules", [])
            self.tracker.context_analyzer.rules = [
                ContextRule(
                    category=r.get("category", ""),
                    title_patterns=r.get("title_patterns", []),
                    sub_category=r.get("sub_category", ""),
                )
                for r in raw_ctx
            ]

        # Update debounce threshold
        if self._pomodoro_manager is not None:
            debounce = config.get("debounce_threshold_seconds", 30)
            self._pomodoro_manager.debounce_threshold = timedelta(seconds=debounce)

        # Handle pending manual task from settings
        pending = config.pop("_pending_manual_task", None)
        if pending and self._pomodoro_manager is not None:
            from datetime import datetime

            self._pomodoro_manager.on_activity(
                pending["category"], pending["sub_category"], datetime.now()
            )

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _show_popup(self, title: str, message: str) -> None:
        """Show a popup with the given message using native macOS dialogs."""
        if sys.platform == "darwin":
            self._osascript_display(title, message)
        else:
            self._fallback_popup(title, message)

    def _show_manual_task_dialog(self) -> None:
        """Show a dialog for creating a manual Pomodoro task."""
        if sys.platform == "darwin":
            self._osascript_manual_task()
        else:
            self._fallback_manual_task()

    # -- macOS native dialogs via osascript --

    def _osascript_display(self, title: str, message: str) -> None:
        """Display text via a native macOS dialog."""
        import subprocess
        # Escape double quotes for AppleScript
        escaped = message.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'display dialog "{escaped}" '
            f'with title "{title}" '
            f'buttons {{"OK"}} default button "OK"'
        )
        try:
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            logger.info("%s:\n%s", title, message)

    def _osascript_manual_task(self) -> None:
        """Prompt for a manual task via native macOS dialogs."""
        import subprocess
        from datetime import datetime

        script_cat = (
            'display dialog "Enter category for the Pomodoro task:" '
            'default answer "Development" '
            'with title "Add Manual Task" '
            'buttons {"Cancel", "OK"} default button "OK"'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script_cat],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                return  # user cancelled
            # Parse "button returned:OK, text returned:Development"
            cat = self._parse_osascript_text(result.stdout)
            if not cat:
                return

            script_sub = (
                f'display dialog "Enter sub-category (optional):" '
                f'default answer "{cat}" '
                f'with title "Add Manual Task" '
                f'buttons {{"Cancel", "OK"}} default button "OK"'
            )
            result = subprocess.run(
                ["osascript", "-e", script_sub],
                capture_output=True, text=True, timeout=60,
            )
            sub = self._parse_osascript_text(result.stdout) or cat

            if self._pomodoro_manager is not None:
                self._pomodoro_manager.on_activity(cat, sub, datetime.now())
                self._osascript_display("Task Started", f"Pomodoro task '{cat}' started.")
        except Exception:
            logger.exception("Failed to create manual task via osascript")

    @staticmethod
    def _parse_osascript_text(output: str) -> str:
        """Extract 'text returned:...' from osascript dialog output."""
        # Output format: "button returned:OK, text returned:value"
        for part in output.split(","):
            part = part.strip()
            if part.startswith("text returned:"):
                return part[len("text returned:"):].strip()
        return ""

    # -- Fallback for non-macOS or when osascript fails --

    def _fallback_popup(self, title: str, message: str) -> None:
        """Log the message when no GUI is available."""
        logger.info("%s:\n%s", title, message)

    def _fallback_manual_task(self) -> None:
        """Log that manual task creation requires a GUI."""
        logger.warning("Manual task dialog not available on this platform")
