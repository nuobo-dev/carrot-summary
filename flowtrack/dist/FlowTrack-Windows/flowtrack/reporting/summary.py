"""Summary generation for daily and weekly activity reports."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from flowtrack.core.models import (
    ActivityRecord,
    CategorySummary,
    DailySummary,
    PomodoroSession,
    SessionStatus,
    WeeklySummary,
)
from flowtrack.persistence.store import ActivityStore


class SummaryGenerator:
    """Produces daily and weekly summaries from persisted activity data.

    Each activity record represents one poll interval of tracked time.
    The *poll_interval* parameter (default 5 seconds) controls how much
    time each record contributes.
    """

    def __init__(
        self, store: ActivityStore, poll_interval: int = 5
    ) -> None:
        self.store = store
        self.poll_interval = poll_interval

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def daily_summary(self, target_date: date) -> DailySummary:
        """Build a summary for *target_date*.

        Queries activities from midnight to midnight, groups by category,
        counts completed Pomodoro sessions per category, and sorts
        categories by total time descending.
        """
        start = datetime(target_date.year, target_date.month, target_date.day)
        end = start + timedelta(days=1)

        activities = self.store.get_activities(start, end)
        sessions = self.store.get_sessions(start, end)

        return self._build_daily(target_date, activities, sessions)

    def weekly_summary(self, start_date: date) -> WeeklySummary:
        """Build a 7-day summary starting from *start_date*.

        Generates a daily summary for each day, then aggregates category
        totals across the entire week.
        """
        daily_breakdowns: list[DailySummary] = []
        for offset in range(7):
            day = start_date + timedelta(days=offset)
            daily_breakdowns.append(self.daily_summary(day))

        # Aggregate categories across all days
        cat_map: dict[str, _CatAccumulator] = {}
        total_time = timedelta()
        total_sessions = 0

        for ds in daily_breakdowns:
            total_time += ds.total_time
            total_sessions += ds.total_sessions
            for cs in ds.categories:
                acc = cat_map.setdefault(
                    cs.category, _CatAccumulator(cs.category)
                )
                acc.total_time += cs.total_time
                acc.completed_sessions += cs.completed_sessions
                for sub, dur in cs.sub_categories.items():
                    acc.sub_categories[sub] = (
                        acc.sub_categories.get(sub, timedelta()) + dur
                    )

        categories = sorted(
            (
                CategorySummary(
                    category=acc.category,
                    sub_categories=dict(acc.sub_categories),
                    total_time=acc.total_time,
                    completed_sessions=acc.completed_sessions,
                )
                for acc in cat_map.values()
            ),
            key=lambda c: c.total_time,
            reverse=True,
        )

        end_date = start_date + timedelta(days=6)
        return WeeklySummary(
            start_date=start_date,
            end_date=end_date,
            daily_breakdowns=daily_breakdowns,
            categories=categories,
            total_time=total_time,
            total_sessions=total_sessions,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_daily(
        self,
        target_date: date,
        activities: list[ActivityRecord],
        sessions: list[PomodoroSession],
    ) -> DailySummary:
        """Aggregate activities and sessions into a single-day summary."""
        interval = timedelta(seconds=self.poll_interval)

        # --- time per (category, sub_category) ---
        time_map: dict[str, dict[str, timedelta]] = defaultdict(
            lambda: defaultdict(timedelta)
        )
        for act in activities:
            time_map[act.category][act.sub_category] += interval

        # --- completed sessions per category ---
        session_counts: dict[str, int] = defaultdict(int)
        for sess in sessions:
            if sess.status == SessionStatus.COMPLETED:
                session_counts[sess.category] += sess.completed_count

        # Merge into CategorySummary list
        all_cats = set(time_map.keys()) | set(session_counts.keys())
        summaries: list[CategorySummary] = []
        for cat in all_cats:
            sub_cats = dict(time_map.get(cat, {}))
            total_time = sum(sub_cats.values(), timedelta())
            summaries.append(
                CategorySummary(
                    category=cat,
                    sub_categories=sub_cats,
                    total_time=total_time,
                    completed_sessions=session_counts.get(cat, 0),
                )
            )

        # Sort by total_time descending
        summaries.sort(key=lambda c: c.total_time, reverse=True)

        total_time = sum((c.total_time for c in summaries), timedelta())
        total_sessions = sum(c.completed_sessions for c in summaries)

        return DailySummary(
            date=target_date,
            categories=summaries,
            total_time=total_time,
            total_sessions=total_sessions,
        )


class _CatAccumulator:
    """Mutable helper for aggregating category data across days."""

    __slots__ = ("category", "sub_categories", "total_time", "completed_sessions")

    def __init__(self, category: str) -> None:
        self.category = category
        self.sub_categories: dict[str, timedelta] = {}
        self.total_time = timedelta()
        self.completed_sessions = 0
