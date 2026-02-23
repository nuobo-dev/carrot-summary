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
        """Auto-create a todo when a new work context is detected."""
        if category == "Other" or not sub_category:
            return
        key = f"{category}::{sub_category}"
        if key in self._seen_contexts:
            return
        self._seen_contexts.add(key)
        try:
            label = sub_category if sub_category != category else category
            self.store.add_todo(f"Work on: {label}", category, auto=True)
        except Exception:
            logger.debug("Could not auto-create todo for %s", key)
