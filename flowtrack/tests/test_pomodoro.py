"""Unit tests for PomodoroManager."""

from datetime import datetime, timedelta

import pytest

from flowtrack.core.models import PomodoroSession, SessionStatus
from flowtrack.core.pomodoro import PomodoroManager


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

T0 = datetime(2025, 1, 1, 9, 0, 0)


def _ts(seconds: int = 0) -> datetime:
    """Return T0 + *seconds*."""
    return T0 + timedelta(seconds=seconds)


# ------------------------------------------------------------------
# get_break_duration
# ------------------------------------------------------------------

class TestGetBreakDuration:
    def test_short_break_for_count_1(self):
        pm = PomodoroManager()
        assert pm.get_break_duration(1) == PomodoroManager.SHORT_BREAK

    def test_short_break_for_count_2(self):
        pm = PomodoroManager()
        assert pm.get_break_duration(2) == PomodoroManager.SHORT_BREAK

    def test_short_break_for_count_3(self):
        pm = PomodoroManager()
        assert pm.get_break_duration(3) == PomodoroManager.SHORT_BREAK

    def test_long_break_for_count_4(self):
        pm = PomodoroManager()
        assert pm.get_break_duration(4) == PomodoroManager.LONG_BREAK

    def test_short_break_for_count_5(self):
        pm = PomodoroManager()
        assert pm.get_break_duration(5) == PomodoroManager.SHORT_BREAK

    def test_long_break_for_count_8(self):
        pm = PomodoroManager()
        assert pm.get_break_duration(8) == PomodoroManager.LONG_BREAK

    def test_short_break_for_count_0(self):
        pm = PomodoroManager()
        assert pm.get_break_duration(0) == PomodoroManager.SHORT_BREAK

    def test_long_break_for_count_12(self):
        pm = PomodoroManager()
        assert pm.get_break_duration(12) == PomodoroManager.LONG_BREAK


# ------------------------------------------------------------------
# on_activity — session start
# ------------------------------------------------------------------

class TestOnActivityStart:
    def test_first_activity_starts_session(self):
        pm = PomodoroManager()
        events = pm.on_activity("Dev", "main.py", T0)
        assert "session_started" in events
        assert pm.active_session is not None
        assert pm.active_session.category == "Dev"
        assert pm.active_session.status == SessionStatus.ACTIVE

    def test_first_activity_sets_sub_category(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        assert pm.active_session.sub_category == "main.py"

    def test_same_category_no_new_events(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        events = pm.on_activity("Dev", "main.py", _ts(5))
        assert events == []

    def test_session_has_uuid_id(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        assert len(pm.active_session.id) > 0


# ------------------------------------------------------------------
# on_activity — debounce and context switching
# ------------------------------------------------------------------

class TestDebounce:
    def test_category_change_starts_debounce(self):
        pm = PomodoroManager(debounce_seconds=30)
        pm.on_activity("Dev", "main.py", T0)
        events = pm.on_activity("Email", "Inbox", _ts(10))
        assert "context_switch_pending" in events
        assert pm.pending_switch is not None

    def test_revert_before_debounce_cancels_switch(self):
        pm = PomodoroManager(debounce_seconds=30)
        pm.on_activity("Dev", "main.py", T0)
        pm.on_activity("Email", "Inbox", _ts(10))
        events = pm.on_activity("Dev", "main.py", _ts(20))
        assert "switch_cancelled" in events
        assert pm.pending_switch is None
        assert pm.active_session.category == "Dev"

    def test_persist_past_debounce_executes_switch(self):
        pm = PomodoroManager(debounce_seconds=30)
        pm.on_activity("Dev", "main.py", T0)
        pm.on_activity("Email", "Inbox", _ts(10))
        # 40s after detection → past 30s threshold
        events = pm.on_activity("Email", "Inbox", _ts(40))
        assert "session_paused" in events
        assert "session_started" in events
        assert pm.active_session.category == "Email"

    def test_original_session_paused_after_switch(self):
        pm = PomodoroManager(debounce_seconds=30)
        pm.on_activity("Dev", "main.py", T0)
        pm.on_activity("Email", "Inbox", _ts(10))
        pm.on_activity("Email", "Inbox", _ts(40))
        assert "Dev" in pm.paused_sessions
        assert pm.paused_sessions["Dev"].status == SessionStatus.PAUSED

    def test_switch_to_third_category_restarts_debounce(self):
        pm = PomodoroManager(debounce_seconds=30)
        pm.on_activity("Dev", "main.py", T0)
        pm.on_activity("Email", "Inbox", _ts(10))
        # Switch to a third category before debounce expires
        events = pm.on_activity("Meetings", "Standup", _ts(20))
        assert "context_switch_pending" in events
        assert pm.pending_switch[0] == "Meetings"


# ------------------------------------------------------------------
# on_activity — session resume
# ------------------------------------------------------------------

class TestSessionResume:
    def test_resume_paused_session(self):
        pm = PomodoroManager(debounce_seconds=10)
        pm.on_activity("Dev", "main.py", T0)
        # Switch to Email
        pm.on_activity("Email", "Inbox", _ts(5))
        pm.on_activity("Email", "Inbox", _ts(15))
        assert pm.active_session.category == "Email"

        # Switch back to Dev
        pm.on_activity("Dev", "main.py", _ts(20))
        pm.on_activity("Dev", "main.py", _ts(30))
        assert "session_resumed" in pm.on_activity("Dev", "main.py", _ts(30)) or \
               pm.active_session.category == "Dev"

    def test_resumed_session_preserves_id(self):
        pm = PomodoroManager(debounce_seconds=10)
        pm.on_activity("Dev", "main.py", T0)
        original_id = pm.active_session.id

        # Switch away
        pm.on_activity("Email", "Inbox", _ts(5))
        pm.on_activity("Email", "Inbox", _ts(15))

        # Switch back
        pm.on_activity("Dev", "main.py", _ts(20))
        pm.on_activity("Dev", "main.py", _ts(30))

        assert pm.active_session.category == "Dev"
        assert pm.active_session.id == original_id

    def test_resumed_session_preserves_elapsed(self):
        pm = PomodoroManager(debounce_seconds=10)
        pm.on_activity("Dev", "main.py", T0)

        # Tick to accumulate some elapsed time
        pm.tick(_ts(60))  # 60 seconds elapsed
        elapsed_before = pm.active_session.elapsed

        # Switch away
        pm.on_activity("Email", "Inbox", _ts(65))
        pm.on_activity("Email", "Inbox", _ts(75))

        # Switch back
        pm.on_activity("Dev", "main.py", _ts(80))
        pm.on_activity("Dev", "main.py", _ts(90))

        assert pm.active_session.category == "Dev"
        assert pm.active_session.elapsed == elapsed_before


# ------------------------------------------------------------------
# tick — work completion and break transitions
# ------------------------------------------------------------------

class TestTick:
    def test_tick_accumulates_elapsed(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        pm.tick(_ts(60))
        assert pm.active_session.elapsed == timedelta(seconds=60)

    def test_tick_no_session_returns_empty(self):
        pm = PomodoroManager()
        events = pm.tick(T0)
        assert events == []

    def test_work_completed_after_25_minutes(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        events = pm.tick(_ts(25 * 60))
        assert "work_completed" in events
        assert "break_started" in events

    def test_completed_count_incremented(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        pm.tick(_ts(25 * 60))
        assert pm.active_session.completed_count == 1

    def test_session_in_break_after_work_completes(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        pm.tick(_ts(25 * 60))
        assert pm.active_session.status == SessionStatus.BREAK

    def test_break_completed_after_short_break(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        # Complete work
        pm.tick(_ts(25 * 60))
        # Complete short break (5 min)
        events = pm.tick(_ts(30 * 60))
        assert "break_completed" in events
        assert pm.active_session.status == SessionStatus.COMPLETED

    def test_long_break_after_4_sessions(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)

        # Simulate 4 work+break cycles
        t = 0
        for i in range(3):
            t += 25 * 60  # work
            pm.tick(_ts(t))
            t += 5 * 60   # short break
            pm.tick(_ts(t))
            # Reset for next work session
            pm.active_session.status = SessionStatus.ACTIVE
            pm.active_session.elapsed = timedelta(0)
            pm._last_tick = _ts(t)

        # 4th work session
        t += 25 * 60
        pm.tick(_ts(t))
        assert pm.active_session.completed_count == 4
        # Should get long break
        break_dur = pm.get_break_duration(pm.active_session.completed_count)
        assert break_dur == PomodoroManager.LONG_BREAK

    def test_tick_incremental_accumulation(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        pm.tick(_ts(30))
        pm.tick(_ts(60))
        assert pm.active_session.elapsed == timedelta(seconds=60)

    def test_break_elapsed_resets_after_work_completion(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        # Tick exactly at 25 min
        pm.tick(_ts(25 * 60))
        # Elapsed should be reset (or near zero) for the break
        assert pm.active_session.elapsed < timedelta(seconds=1)

    def test_tick_paused_session_does_not_accumulate(self):
        pm = PomodoroManager(debounce_seconds=10)
        pm.on_activity("Dev", "main.py", T0)
        pm.tick(_ts(60))
        elapsed_at_pause = pm.active_session.elapsed

        # Pause via context switch
        pm.on_activity("Email", "Inbox", _ts(65))
        pm.on_activity("Email", "Inbox", _ts(75))

        # The paused session should retain its elapsed
        paused = pm.paused_sessions["Dev"]
        assert paused.elapsed == elapsed_at_pause


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------

class TestEdgeCases:
    def test_debounce_exactly_at_threshold(self):
        pm = PomodoroManager(debounce_seconds=30)
        pm.on_activity("Dev", "main.py", T0)
        pm.on_activity("Email", "Inbox", _ts(10))
        # Exactly at threshold (10 + 30 = 40)
        events = pm.on_activity("Email", "Inbox", _ts(40))
        assert "session_paused" in events

    def test_multiple_paused_sessions(self):
        pm = PomodoroManager(debounce_seconds=10)
        pm.on_activity("Dev", "main.py", T0)

        # Switch to Email
        pm.on_activity("Email", "Inbox", _ts(5))
        pm.on_activity("Email", "Inbox", _ts(15))

        # Switch to Meetings
        pm.on_activity("Meetings", "Standup", _ts(20))
        pm.on_activity("Meetings", "Standup", _ts(30))

        assert "Dev" in pm.paused_sessions
        assert "Email" in pm.paused_sessions
        assert pm.active_session.category == "Meetings"

    def test_zero_debounce_immediate_switch(self):
        pm = PomodoroManager(debounce_seconds=0)
        pm.on_activity("Dev", "main.py", T0)
        events = pm.on_activity("Email", "Inbox", _ts(1))
        # With 0 debounce, the pending switch is created
        assert "context_switch_pending" in events
        # Next observation at same category should trigger switch
        events = pm.on_activity("Email", "Inbox", _ts(1))
        assert "session_paused" in events

    def test_session_started_has_zero_elapsed(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        assert pm.active_session.elapsed == timedelta(0)

    def test_session_started_has_zero_completed_count(self):
        pm = PomodoroManager()
        pm.on_activity("Dev", "main.py", T0)
        assert pm.active_session.completed_count == 0
