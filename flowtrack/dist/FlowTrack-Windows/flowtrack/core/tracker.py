"""Tracker orchestrator for FlowTrack.

Coordinates the polling loop: reads the active window, classifies the
activity, analyzes context, updates the Pomodoro manager, and persists
the observation to the activity store.
"""

import logging
import time
from datetime import datetime
from typing import Optional

from flowtrack.core.classifier import Classifier
from flowtrack.core.context_analyzer import ContextAnalyzer
from flowtrack.core.models import ActivityRecord
from flowtrack.core.pomodoro import PomodoroManager
from flowtrack.persistence.store import ActivityStore
from flowtrack.platform.base import WindowProvider

logger = logging.getLogger(__name__)


class Tracker:
    """Orchestrates the activity-tracking pipeline.

    Each call to :meth:`poll_once` executes one full cycle:

    1. ``window_provider.get_active_window()`` → ``WindowInfo``
    2. ``classifier.classify(app_name, window_title)`` → ``Work_Category``
    3. ``context_analyzer.analyze(...)`` → ``ContextResult``
    4. ``pomodoro_manager.on_activity(...)`` → events
    5. ``pomodoro_manager.tick(now)`` → events
    6. ``store.save_activity(...)`` — persist the observation
    7. If the pomodoro session changed, ``store.save_session(session)``

    :meth:`run` drives the loop at a configurable interval, skipping
    polls when the user is idle.
    """

    def __init__(
        self,
        window_provider: WindowProvider,
        classifier: Classifier,
        context_analyzer: ContextAnalyzer,
        pomodoro_manager: PomodoroManager,
        store: ActivityStore,
        poll_interval: int = 5,
    ) -> None:
        self.window_provider = window_provider
        self.classifier = classifier
        self.context_analyzer = context_analyzer
        self.pomodoro_manager = pomodoro_manager
        self.store = store
        self.poll_interval = poll_interval
        self._running = False
        self._seen_contexts: set[str] = set()

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

        # 2. Classify
        category = self.classifier.classify(
            window_info.app_name, window_info.window_title
        )

        # 3. Analyze context
        context = self.context_analyzer.analyze(
            window_info.app_name, window_info.window_title, category
        )

        # 4. Update pomodoro
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
        )
        self.store.save_activity(record)

        # 7. Persist session state if one exists
        if self.pomodoro_manager.active_session is not None:
            self.store.save_session(self.pomodoro_manager.active_session)

        # 8. Auto-generate todo for new sub-categories
        self._maybe_create_todo(context.category, context.sub_category)

    def run(self) -> None:
        """Main loop: poll at configured interval, skip when idle (Req 1.4)."""
        self._running = True
        while self._running:
            # Check idle before polling
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
