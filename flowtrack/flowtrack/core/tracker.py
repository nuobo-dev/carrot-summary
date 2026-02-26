"""Tracker orchestrator for CarrotSummary.

Coordinates activity tracking via either:
- Event-driven mode (macOS): NSWorkspace notifications + lightweight title polling
- Polling mode (fallback/Windows): periodic full window queries

Also supports optional ML-powered screen analysis for richer activity summaries.
"""

import logging
import sys
import time
from datetime import datetime
from typing import Optional

from flowtrack.core.classifier import Classifier
from flowtrack.core.context_analyzer import ContextAnalyzer
from flowtrack.core.models import ActivityRecord, WindowInfo
from flowtrack.core.pomodoro import PomodoroManager
from flowtrack.persistence.store import ActivityStore
from flowtrack.platform.base import WindowProvider

logger = logging.getLogger(__name__)


class Tracker:
    """Orchestrates the activity-tracking pipeline.

    Supports two modes:
    - **Event-driven** (macOS): Uses MacOSWindowObserver for app switch
      notifications + lightweight title polling. Only processes changes.
    - **Polling** (fallback): Traditional poll loop every N seconds.

    Optional ML screen analysis can be toggled on/off at runtime.
    """

    def __init__(
        self,
        window_provider: WindowProvider,
        classifier: Classifier,
        context_analyzer: ContextAnalyzer,
        pomodoro_manager: PomodoroManager,
        store: ActivityStore,
        poll_interval: int = 5,
        ml_screen_analysis: bool = False,
    ) -> None:
        self.window_provider = window_provider
        self.classifier = classifier
        self.context_analyzer = context_analyzer
        self.pomodoro_manager = pomodoro_manager
        self.store = store
        self.poll_interval = poll_interval
        self._running = False
        self._seen_contexts: set[str] = set()
        self.current_active_task_id: Optional[int] = None
        self._observer = None  # MacOSWindowObserver when in event-driven mode
        self._screen_analyzer = None
        self._last_window_info: Optional[WindowInfo] = None
        self._last_context = None
        self.debug_mode = False
        self._debug_log: list[dict] = []  # ring buffer of recent debug entries
        self._debug_max = 100

        # Initialize ML screen analyzer if enabled
        if ml_screen_analysis:
            self._init_screen_analyzer()

    @property
    def ml_enabled(self) -> bool:
        """Whether ML screen analysis is currently enabled."""
        return self._screen_analyzer is not None and self._screen_analyzer.enabled

    @ml_enabled.setter
    def ml_enabled(self, value: bool) -> None:
        """Toggle ML screen analysis on/off at runtime."""
        if value and self._screen_analyzer is None:
            self._init_screen_analyzer()
        elif value and self._screen_analyzer is not None:
            self._screen_analyzer.enabled = True
        elif not value and self._screen_analyzer is not None:
            self._screen_analyzer.enabled = False

    def _init_screen_analyzer(self) -> None:
        """Lazily initialize the screen analyzer."""
        try:
            from flowtrack.core.screen_analyzer import ScreenAnalyzer
            self._screen_analyzer = ScreenAnalyzer(enabled=True)
            logger.info("ML screen analysis initialized")
        except Exception:
            logger.info("ML screen analysis not available on this platform")
            self._screen_analyzer = None

    def poll_once(self, now: datetime) -> None:
        """Execute a single poll cycle."""

        # 1. Get active window — handle errors gracefully (Req 1.3)
        try:
            window_info = self.window_provider.get_active_window()
        except Exception:
            logger.exception("Failed to get active window; skipping this cycle")
            return

        if window_info is None:
            logger.debug("No active window returned; skipping this cycle")
            return

        self._process_window(window_info, now)

    def on_window_change(self, window_info: WindowInfo, now: datetime) -> None:
        """Called by the event-driven observer when the active window changes."""
        self._process_window(window_info, now)

    def _process_window(self, window_info: WindowInfo, now: datetime) -> None:
        """Core processing pipeline for a window observation."""

        # 2. Classify
        category = self.classifier.classify(
            window_info.app_name, window_info.window_title
        )

        # 3. Analyze context (regex-based)
        context = self.context_analyzer.analyze(
            window_info.app_name, window_info.window_title, category
        )

        # 3b. ML screen analysis override (if enabled)
        ml_summary = None
        ml_used = False
        if self._screen_analyzer and self._screen_analyzer.enabled:
            try:
                ml_summary = self._screen_analyzer.analyze_screen(
                    window_info.app_name, window_info.window_title
                )
                if ml_summary:
                    ml_used = True
                    context.activity_summary = ml_summary
            except Exception:
                logger.debug("ML screen analysis failed, using regex summary")

        # Debug logging
        if self.debug_mode:
            entry = {
                "timestamp": now.isoformat(),
                "app_name": window_info.app_name,
                "window_title": window_info.window_title,
                "category": category,
                "sub_category": context.sub_category,
                "context_label": context.context_label,
                "activity_summary": context.activity_summary,
                "ml_used": ml_used,
                "ml_raw_summary": ml_summary,
                "active_task_id": self.current_active_task_id,
                "session_id": self.pomodoro_manager.active_session.id if self.pomodoro_manager.active_session else None,
                "session_status": self.pomodoro_manager.active_session.status.value if self.pomodoro_manager.active_session else None,
            }
            self._debug_log.append(entry)
            if len(self._debug_log) > self._debug_max:
                self._debug_log = self._debug_log[-self._debug_max:]

        # Cache for periodic recording in event-driven mode
        self._last_window_info = window_info
        self._last_context = context

        # 4. Update pomodoro (propagate active task to session)
        self.pomodoro_manager.active_task_id = self.current_active_task_id
        self.pomodoro_manager.on_activity(
            context.category, context.sub_category, now
        )

        # 5. Tick pomodoro timer
        self.pomodoro_manager.tick(now)

        # 6. Persist activity record
        session_id: Optional[str] = None
        if self.pomodoro_manager.active_session is not None:
            session_id = self.pomodoro_manager.active_session.id

        record = ActivityRecord(
            id=0,
            timestamp=now,
            app_name=window_info.app_name,
            window_title=window_info.window_title,
            category=context.category,
            sub_category=context.sub_category,
            session_id=session_id,
            active_task_id=self.current_active_task_id,
            activity_summary=context.activity_summary,
        )
        self.store.save_activity(record)

        # 7. Persist session state if one exists
        if self.pomodoro_manager.active_session is not None:
            self.store.save_session(self.pomodoro_manager.active_session)

        # 8. Auto-generate todo for new sub-categories
        self._maybe_create_todo(context.category, context.sub_category)

    def run(self) -> None:
        """Main loop: uses event-driven observer on macOS, falls back to polling.

        On macOS, starts a MacOSWindowObserver that fires callbacks on window
        changes. The Pomodoro timer still needs periodic ticking, so we keep
        a lightweight tick loop.

        On other platforms, falls back to the traditional poll loop.
        """
        self._running = True

        # Try event-driven mode on macOS
        if sys.platform == "darwin" and self._try_start_observer():
            logger.info("Running in event-driven mode (macOS observer)")
            self._run_tick_loop()
        else:
            logger.info("Running in polling mode (interval=%ds)", self.poll_interval)
            self._run_poll_loop()

    def _try_start_observer(self) -> bool:
        """Try to start the macOS event-driven observer."""
        try:
            from flowtrack.platform.macos import MacOSWindowProvider
            from flowtrack.platform.macos_observer import MacOSWindowObserver

            if not isinstance(self.window_provider, MacOSWindowProvider):
                return False

            self._observer = MacOSWindowObserver(
                provider=self.window_provider,
                on_change=self.on_window_change,
                title_check_interval=self.poll_interval,
            )
            self._observer.start()
            return True
        except ImportError:
            return False
        except Exception:
            logger.debug("Failed to start macOS observer", exc_info=True)
            return False

    def _run_tick_loop(self) -> None:
        """Tick loop for event-driven mode.

        The observer handles window change detection and calls on_window_change.
        This loop periodically:
        1. Ticks the Pomodoro timer
        2. Saves an activity record for the current window (so time accumulates)
        3. Persists session state
        """
        while self._running:
            try:
                idle = self.window_provider.is_user_idle()
            except Exception:
                idle = False

            if not idle:
                now = datetime.now()
                self.pomodoro_manager.tick(now)

                # Save a periodic activity record so time accumulates
                if self._last_window_info is not None and self._last_context is not None:
                    session_id = None
                    if self.pomodoro_manager.active_session is not None:
                        session_id = self.pomodoro_manager.active_session.id

                    record = ActivityRecord(
                        id=0,
                        timestamp=now,
                        app_name=self._last_window_info.app_name,
                        window_title=self._last_window_info.window_title,
                        category=self._last_context.category,
                        sub_category=self._last_context.sub_category,
                        session_id=session_id,
                        active_task_id=self.current_active_task_id,
                        activity_summary=self._last_context.activity_summary,
                    )
                    try:
                        self.store.save_activity(record)
                    except Exception:
                        logger.debug("Failed to save periodic activity record")

                # Persist session state
                if self.pomodoro_manager.active_session is not None:
                    try:
                        self.store.save_session(self.pomodoro_manager.active_session)
                    except Exception:
                        logger.debug("Failed to persist session in tick loop")

            time.sleep(self.poll_interval)

        # Clean up observer
        if self._observer is not None:
            self._observer.stop()
            self._observer = None

    def _run_poll_loop(self) -> None:
        """Traditional polling loop (fallback for non-macOS)."""
        while self._running:
            try:
                idle = self.window_provider.is_user_idle()
            except Exception:
                logger.exception("Failed to check idle state; assuming not idle")
                idle = False

            if not idle:
                self.poll_once(datetime.now())
            else:
                logger.debug("User is idle; skipping poll")

            time.sleep(self.poll_interval)

    def stop(self) -> None:
        """Signal the run loop to stop."""
        self._running = False

    def _maybe_create_todo(self, category: str, sub_category: str) -> None:
        """Auto-create a todo when a meaningful new work context is detected.

        Skips generic/unhelpful labels (just the category name, app names,
        or very short strings). Deduplicates against both the in-memory
        seen set and existing todos in the database.
        """
        if category == "Other" or not sub_category:
            return

        # Skip if the sub_category is just the category name (no real context)
        if sub_category.lower() == category.lower():
            return

        # Skip very short or generic labels
        if len(sub_category) < 5:
            return

        # Skip labels that are just app names
        _SKIP_NAMES = {
            "google chrome", "firefox", "safari", "edge", "brave", "arc",
            "chrome", "opera", "slack", "discord", "zoom", "teams",
            "outlook", "mail", "terminal", "iterm", "finder", "explorer",
            "code", "vs code", "visual studio code", "electron",
        }
        if sub_category.lower().strip() in _SKIP_NAMES:
            return

        # In-memory dedup
        key = f"{category}::{sub_category}"
        if key in self._seen_contexts:
            return
        self._seen_contexts.add(key)

        # Database dedup — check if a todo with similar title already exists
        try:
            existing = self.store.get_todos(include_done=True)
            normalized = _normalize_todo(sub_category)
            for todo in existing:
                if _normalize_todo(todo.get("title", "")) == normalized:
                    return
        except Exception:
            pass

        try:
            # Find a manual parent bucket for this category, or create a general one
            parent_id = self._find_or_create_bucket(category)
            self.store.add_todo(sub_category, category, auto=True, parent_id=parent_id)
        except Exception:
            logger.debug("Could not auto-create todo for %s", key)

    def _find_or_create_bucket(self, category: str) -> int | None:
        """Find a manual work bucket for this category, or create a general one."""
        try:
            todos = self.store.get_todos(include_done=True)
            # Look for an existing manual (non-auto) top-level todo matching this category
            for t in todos:
                if not t.get("auto_generated") and not t.get("parent_id") and t.get("category", "").lower() == category.lower():
                    return t["id"]
            # No manual bucket found — create a general one
            bucket_id = self.store.add_todo(f"General: {category}", category, auto=False, parent_id=None)
            return bucket_id
        except Exception:
            return None


def _normalize_todo(title: str) -> str:
    """Normalize a todo title for dedup comparison."""
    import re
    t = title.lower().strip()
    # Strip common prefixes we used to add
    t = re.sub(r"^work on:\s*", "", t)
    t = re.sub(r"^(writing|emailing|browsing|coding|designing|meeting|chat|task|spreadsheet|presentation):\s*", "", t)
    return t.strip()
