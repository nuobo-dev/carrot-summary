"""Unit tests for TextFormatter."""

from datetime import date, timedelta

import pytest

from flowtrack.core.models import CategorySummary, DailySummary, WeeklySummary
from flowtrack.reporting.formatter import TextFormatter


# ------------------------------------------------------------------
# format_duration
# ------------------------------------------------------------------

class TestFormatDuration:
    def test_zero(self):
        assert TextFormatter.format_duration(timedelta()) == "0m"

    def test_minutes_only(self):
        assert TextFormatter.format_duration(timedelta(minutes=45)) == "45m"

    def test_hours_and_minutes(self):
        assert TextFormatter.format_duration(timedelta(hours=2, minutes=15)) == "2h 15m"

    def test_hours_only(self):
        assert TextFormatter.format_duration(timedelta(hours=3)) == "3h 0m"

    def test_truncates_seconds(self):
        # 2h 15m 30s should truncate to 2h 15m
        assert TextFormatter.format_duration(timedelta(hours=2, minutes=15, seconds=30)) == "2h 15m"

    def test_large_duration(self):
        assert TextFormatter.format_duration(timedelta(hours=100, minutes=5)) == "100h 5m"

    def test_one_minute(self):
        assert TextFormatter.format_duration(timedelta(minutes=1)) == "1m"

    def test_59_minutes(self):
        assert TextFormatter.format_duration(timedelta(minutes=59)) == "59m"

    def test_exactly_one_hour(self):
        assert TextFormatter.format_duration(timedelta(hours=1)) == "1h 0m"

    def test_negative_treated_as_zero(self):
        assert TextFormatter.format_duration(timedelta(seconds=-10)) == "0m"


# ------------------------------------------------------------------
# parse_duration
# ------------------------------------------------------------------

class TestParseDuration:
    def test_hours_and_minutes(self):
        assert TextFormatter.parse_duration("2h 15m") == timedelta(hours=2, minutes=15)

    def test_hours_only(self):
        assert TextFormatter.parse_duration("3h") == timedelta(hours=3)

    def test_minutes_only(self):
        assert TextFormatter.parse_duration("45m") == timedelta(minutes=45)

    def test_zero_minutes(self):
        assert TextFormatter.parse_duration("0m") == timedelta()

    def test_zero_hours_zero_minutes(self):
        assert TextFormatter.parse_duration("0h 0m") == timedelta()

    def test_hours_zero_minutes(self):
        assert TextFormatter.parse_duration("3h 0m") == timedelta(hours=3)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            TextFormatter.parse_duration("abc")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            TextFormatter.parse_duration("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            TextFormatter.parse_duration("   ")


# ------------------------------------------------------------------
# format/parse round-trip
# ------------------------------------------------------------------

class TestDurationRoundTrip:
    @pytest.mark.parametrize("duration", [
        timedelta(),
        timedelta(minutes=1),
        timedelta(minutes=59),
        timedelta(hours=1),
        timedelta(hours=2, minutes=15),
        timedelta(hours=10, minutes=0),
        timedelta(hours=99, minutes=59),
    ])
    def test_round_trip(self, duration: timedelta):
        text = TextFormatter.format_duration(duration)
        parsed = TextFormatter.parse_duration(text)
        assert parsed == duration

    def test_round_trip_truncates_seconds(self):
        original = timedelta(hours=1, minutes=30, seconds=45)
        text = TextFormatter.format_duration(original)
        parsed = TextFormatter.parse_duration(text)
        # Should equal the truncated-to-minutes version
        assert parsed == timedelta(hours=1, minutes=30)


# ------------------------------------------------------------------
# format_daily
# ------------------------------------------------------------------

class TestFormatDaily:
    def test_empty_summary(self):
        summary = DailySummary(date=date(2025, 6, 15))
        result = TextFormatter.format_daily(summary)
        assert "Daily Summary" in result
        assert "June 15, 2025" in result
        assert "No activity recorded" in result

    def test_single_category(self):
        summary = DailySummary(
            date=date(2025, 6, 15),
            categories=[
                CategorySummary(
                    category="Development",
                    total_time=timedelta(hours=2, minutes=15),
                    completed_sessions=3,
                ),
            ],
            total_time=timedelta(hours=2, minutes=15),
            total_sessions=3,
        )
        result = TextFormatter.format_daily(summary)
        assert "Development" in result
        assert "2h 15m" in result
        assert "3" in result
        assert "Total" in result

    def test_multiple_categories_aligned(self):
        summary = DailySummary(
            date=date(2025, 6, 15),
            categories=[
                CategorySummary(
                    category="Development",
                    total_time=timedelta(hours=3),
                    completed_sessions=4,
                ),
                CategorySummary(
                    category="Email",
                    total_time=timedelta(minutes=45),
                    completed_sessions=1,
                ),
            ],
            total_time=timedelta(hours=3, minutes=45),
            total_sessions=5,
        )
        result = TextFormatter.format_daily(summary)
        assert "Development" in result
        assert "Email" in result
        assert "Total" in result
        assert "3h 45m" in result

    def test_header_contains_date(self):
        summary = DailySummary(date=date(2025, 1, 1))
        result = TextFormatter.format_daily(summary)
        assert "Wednesday, January 01, 2025" in result

    def test_contains_column_headers(self):
        summary = DailySummary(
            date=date(2025, 6, 15),
            categories=[
                CategorySummary(
                    category="Dev",
                    total_time=timedelta(hours=1),
                    completed_sessions=1,
                ),
            ],
            total_time=timedelta(hours=1),
            total_sessions=1,
        )
        result = TextFormatter.format_daily(summary)
        assert "Category" in result
        assert "Time" in result
        assert "Sessions" in result


# ------------------------------------------------------------------
# format_weekly
# ------------------------------------------------------------------

class TestFormatWeekly:
    def test_empty_week(self):
        summary = WeeklySummary(
            start_date=date(2025, 6, 9),
            end_date=date(2025, 6, 15),
            daily_breakdowns=[
                DailySummary(date=date(2025, 6, 9) + timedelta(days=i))
                for i in range(7)
            ],
        )
        result = TextFormatter.format_weekly(summary)
        assert "Weekly Summary" in result
        assert "June 09, 2025" in result
        assert "June 15, 2025" in result
        assert "No activity" in result

    def test_weekly_with_data(self):
        daily = DailySummary(
            date=date(2025, 6, 9),
            categories=[
                CategorySummary(
                    category="Dev",
                    total_time=timedelta(hours=4),
                    completed_sessions=6,
                ),
            ],
            total_time=timedelta(hours=4),
            total_sessions=6,
        )
        empty_days = [
            DailySummary(date=date(2025, 6, 9) + timedelta(days=i))
            for i in range(1, 7)
        ]
        summary = WeeklySummary(
            start_date=date(2025, 6, 9),
            end_date=date(2025, 6, 15),
            daily_breakdowns=[daily] + empty_days,
            categories=[
                CategorySummary(
                    category="Dev",
                    total_time=timedelta(hours=4),
                    completed_sessions=6,
                ),
            ],
            total_time=timedelta(hours=4),
            total_sessions=6,
        )
        result = TextFormatter.format_weekly(summary)
        assert "Weekly Totals" in result
        assert "Daily Breakdown" in result
        assert "Dev" in result
        assert "4h 0m" in result

    def test_weekly_contains_all_days(self):
        daily_breakdowns = [
            DailySummary(date=date(2025, 6, 9) + timedelta(days=i))
            for i in range(7)
        ]
        summary = WeeklySummary(
            start_date=date(2025, 6, 9),
            end_date=date(2025, 6, 15),
            daily_breakdowns=daily_breakdowns,
        )
        result = TextFormatter.format_weekly(summary)
        assert "Monday, June 09" in result
        assert "Sunday, June 15" in result
