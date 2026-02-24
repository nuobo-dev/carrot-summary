"""Pomodoro Manager for CarrotSummary.

Manages Pomodoro sessions with automatic context-switch detection via
debounce logic.  Sessions are keyed by Work_Category so that returning
to a previously paused category resumes the existing session.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from flowtrack.core.models import PomodoroSession, SessionStatus


class PomodoroManager:
    """Manages Pomodoro work/break sessions with debounce-based context switching."""

    WORK_DURATION = timedelta(minutes=25)
    SHORT_BREAK = timedelta(minutes=5)
    LONG_BREAK = timedelta(minutes=15)
    LONG_BREAK_INTERVAL = 4

    def __init__(self, debounce_seconds: int = 30):
        self.debounce_threshold = timedelta(seconds=debounce_seconds)
        self.active_session: Optional[PomodoroSession] = None
        self.paused_sessions: dict[str, PomodoroSession] = {}  # keyed by category
        self.pending_switch: Optional[tuple[str, str, datetime]] = None  # (category, sub_cat, detected_at)
        self._last_tick: Optional[datetime] = None
        self.active_task_id: Optional[int] = None  # set by Tracker from current_active_task_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_activity(self, category: str, sub_category: str, timestamp: datetime) -> list[str]:
        """Process an activity observation.

        Returns a list of event strings that occurred:
        - ``'session_started'``  – a brand-new session was created
        - ``'session_resumed'``  – a previously paused session was resumed
        - ``'session_paused'``   – the active session was paused
        - ``'context_switch_pending'`` – debounce timer started for a new category
        - ``'switch_cancelled'`` – pending switch was cancelled (reverted category)
        """
        events: list[str] = []

        # --- No active session yet: start one ---
        if self.active_session is None:
            events.extend(self._start_or_resume(category, sub_category, timestamp))
            self.pending_switch = None
            return events

        current_category = self.active_session.category

        # --- Same category as active session ---
        if category == current_category:
            if self.pending_switch is not None:
                events.append("switch_cancelled")
                self.pending_switch = None
            return events

        # --- Different category ---
        # If there's already a pending switch…
        if self.pending_switch is not None:
            pending_cat, pending_sub, detected_at = self.pending_switch

            if category == pending_cat:
                # Still the new category – check if debounce expired
                if timestamp - detected_at >= self.debounce_threshold:
                    events.extend(self._execute_switch(category, sub_category, timestamp))
                # else: still waiting, nothing to do
                return events

            if category == current_category:
                # Reverted to original category
                events.append("switch_cancelled")
                self.pending_switch = None
                return events

            # Switched to a *third* category – restart debounce
            self.pending_switch = (category, sub_category, timestamp)
            events.append("context_switch_pending")
            return events

        # No pending switch yet – start debounce
        self.pending_switch = (category, sub_category, timestamp)
        events.append("context_switch_pending")
        return events

    def tick(self, now: datetime) -> list[str]:
        """Advance timer state.  Should be called periodically.

        Returns a list of event strings:
        - ``'work_completed'``  – work interval finished
        - ``'break_started'``   – break interval began
        - ``'break_completed'`` – break interval finished
        """
        events: list[str] = []

        if self.active_session is None:
            self._last_tick = now
            return events

        # Accumulate elapsed time since last tick
        if self._last_tick is not None and self.active_session.status in (
            SessionStatus.ACTIVE,
            SessionStatus.BREAK,
        ):
            delta = now - self._last_tick
            if delta > timedelta(0):
                self.active_session.elapsed += delta

        self._last_tick = now

        # --- ACTIVE session: check for work completion ---
        if self.active_session.status == SessionStatus.ACTIVE:
            if self.active_session.elapsed >= self.WORK_DURATION:
                self.active_session.completed_count += 1
                self.active_session.status = SessionStatus.BREAK
                # Reset elapsed for the break interval
                overflow = self.active_session.elapsed - self.WORK_DURATION
                self.active_session.elapsed = overflow
                events.append("work_completed")
                events.append("break_started")

        # --- BREAK session: check for break completion ---
        elif self.active_session.status == SessionStatus.BREAK:
            break_dur = self.get_break_duration(self.active_session.completed_count)
            if self.active_session.elapsed >= break_dur:
                # Auto-restart: begin next work interval immediately
                overflow = self.active_session.elapsed - break_dur
                self.active_session.status = SessionStatus.ACTIVE
                self.active_session.elapsed = overflow
                events.append("break_completed")
                events.append("work_started")

        return events

    def get_break_duration(self, completed_count: int) -> timedelta:
        """Return the appropriate break duration based on completed count.

        Long break (15 min) when *completed_count* is a positive multiple of 4,
        short break (5 min) otherwise.
        """
        if completed_count > 0 and completed_count % self.LONG_BREAK_INTERVAL == 0:
            return self.LONG_BREAK
        return self.SHORT_BREAK

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_or_resume(self, category: str, sub_category: str, timestamp: datetime) -> list[str]:
        """Start a new session or resume a paused one for *category*."""
        events: list[str] = []

        if category in self.paused_sessions:
            session = self.paused_sessions.pop(category)
            session.status = SessionStatus.ACTIVE
            session.active_task_id = self.active_task_id
            self.active_session = session
            self._last_tick = timestamp
            events.append("session_resumed")
        else:
            self.active_session = PomodoroSession(
                id=str(uuid.uuid4()),
                category=category,
                sub_category=sub_category,
                start_time=timestamp,
                elapsed=timedelta(0),
                status=SessionStatus.ACTIVE,
                completed_count=0,
                active_task_id=self.active_task_id,
            )
            self._last_tick = timestamp
            events.append("session_started")

        return events

    def _execute_switch(self, category: str, sub_category: str, timestamp: datetime) -> list[str]:
        """Pause the active session and start/resume the target category."""
        events: list[str] = []

        # Pause current
        if self.active_session is not None:
            self.active_session.status = SessionStatus.PAUSED
            self.paused_sessions[self.active_session.category] = self.active_session
            self.active_session = None
            events.append("session_paused")

        # Start or resume target
        events.extend(self._start_or_resume(category, sub_category, timestamp))
        self.pending_switch = None
        return events
