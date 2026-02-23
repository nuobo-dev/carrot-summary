"""Text formatter for FlowTrack summaries.

Renders DailySummary and WeeklySummary as aligned plain-text reports,
and provides duration format/parse utilities.
"""

import re
from datetime import timedelta

from flowtrack.core.models import CategorySummary, DailySummary, WeeklySummary


class TextFormatter:
    """Formats summary data as human-readable plain text."""

    # Pattern for parsing duration strings like "2h 15m", "2h", "15m", "0m"
    _DURATION_RE = re.compile(
        r"^\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*$"
    )

    @staticmethod
    def format_duration(duration: timedelta) -> str:
        """Format a timedelta as 'Xh Ym' (e.g., '2h 15m').

        Truncates to whole minutes. Returns '0m' for zero/negative durations.
        """
        total_seconds = int(duration.total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        total_minutes = total_seconds // 60
        hours = total_minutes // 60
        minutes = total_minutes % 60

        if hours == 0:
            return f"{minutes}m"
        return f"{hours}h {minutes}m"

    @staticmethod
    def parse_duration(text: str) -> timedelta:
        """Parse 'Xh Ym', 'Xh', or 'Ym' back to a timedelta.

        Raises ValueError if the text doesn't match the expected format.
        """
        match = TextFormatter._DURATION_RE.match(text)
        if not match or (match.group(1) is None and match.group(2) is None):
            raise ValueError(f"Invalid duration format: {text!r}")

        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        return timedelta(hours=hours, minutes=minutes)

    @staticmethod
    def _format_category_table(
        categories: list[CategorySummary],
        total_time: timedelta,
        total_sessions: int,
    ) -> str:
        """Render a category table with aligned columns.

        Returns lines like:
          Category            Time       Sessions
          ─────────────────────────────────────────
          Development         2h 15m            3
          Email               0h 45m            1
          ─────────────────────────────────────────
          Total               3h 0m             4
        """
        if not categories:
            return "  No activity recorded.\n"

        # Determine column widths
        cat_width = max(len(c.category) for c in categories)
        cat_width = max(cat_width, len("Category"), len("Total"))

        dur_strs = [TextFormatter.format_duration(c.total_time) for c in categories]
        total_dur_str = TextFormatter.format_duration(total_time)
        dur_width = max(len(s) for s in dur_strs + [total_dur_str])
        dur_width = max(dur_width, len("Time"))

        sess_strs = [str(c.completed_sessions) for c in categories]
        total_sess_str = str(total_sessions)
        sess_width = max(len(s) for s in sess_strs + [total_sess_str])
        sess_width = max(sess_width, len("Sessions"))

        # Build header
        header = (
            f"  {'Category':<{cat_width}}  "
            f"{'Time':>{dur_width}}  "
            f"{'Sessions':>{sess_width}}"
        )
        sep_len = len(header)
        separator = "  " + "\u2500" * (sep_len - 2)

        lines = [header, separator]

        # Data rows
        for cat, dur_str, sess_str in zip(categories, dur_strs, sess_strs):
            lines.append(
                f"  {cat.category:<{cat_width}}  "
                f"{dur_str:>{dur_width}}  "
                f"{sess_str:>{sess_width}}"
            )

        # Total row
        lines.append(separator)
        lines.append(
            f"  {'Total':<{cat_width}}  "
            f"{total_dur_str:>{dur_width}}  "
            f"{total_sess_str:>{sess_width}}"
        )

        return "\n".join(lines) + "\n"

    @staticmethod
    def format_daily(summary: DailySummary) -> str:
        """Render a daily summary as aligned plain text."""
        header = f"Daily Summary: {summary.date.strftime('%A, %B %d, %Y')}\n"
        body = TextFormatter._format_category_table(
            summary.categories, summary.total_time, summary.total_sessions
        )
        return header + "\n" + body

    @staticmethod
    def format_weekly(summary: WeeklySummary) -> str:
        """Render a weekly summary as aligned plain text."""
        start_str = summary.start_date.strftime("%B %d, %Y")
        end_str = summary.end_date.strftime("%B %d, %Y")
        parts: list[str] = []

        parts.append(f"Weekly Summary: {start_str} - {end_str}\n")

        # Weekly totals
        parts.append("\nWeekly Totals:\n")
        parts.append(
            TextFormatter._format_category_table(
                summary.categories, summary.total_time, summary.total_sessions
            )
        )

        # Daily breakdowns
        parts.append("\nDaily Breakdown:\n")
        for daily in summary.daily_breakdowns:
            day_label = daily.date.strftime("%A, %B %d")
            if not daily.categories:
                parts.append(f"\n  {day_label}: No activity\n")
            else:
                parts.append(f"\n  {day_label}:\n")
                parts.append(
                    TextFormatter._format_category_table(
                        daily.categories, daily.total_time, daily.total_sessions
                    )
                )

        return "".join(parts)
