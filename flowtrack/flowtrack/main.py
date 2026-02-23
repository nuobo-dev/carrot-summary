"""FlowTrack application entry point.

Supports two modes:
  - GUI mode (default): launches the system tray application
  - CLI mode: prints a daily or weekly summary to stdout

Usage:
    python -m flowtrack.main              # GUI mode
    python -m flowtrack.main --daily      # print today's daily summary
    python -m flowtrack.main --weekly     # print this week's weekly summary
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta

from flowtrack.core.config import get_default_config_path, load_config
from flowtrack.persistence.store import ActivityStore
from flowtrack.reporting.formatter import TextFormatter
from flowtrack.reporting.summary import SummaryGenerator


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="flowtrack",
        description="FlowTrack — cross-platform productivity tracker",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--daily",
        action="store_true",
        help="Print today's daily summary and exit",
    )
    group.add_argument(
        "--weekly",
        action="store_true",
        help="Print this week's weekly summary and exit",
    )
    return parser


def _print_daily_summary(config: dict) -> None:
    """Create a store and summary generator, then print today's summary."""
    db_path = os.path.expanduser(config.get("database_path", "~/.flowtrack/flowtrack.db"))
    store = ActivityStore(db_path)
    store.init_db()
    try:
        poll_interval = config.get("poll_interval_seconds", 5)
        generator = SummaryGenerator(store, poll_interval)
        summary = generator.daily_summary(date.today())
        print(TextFormatter.format_daily(summary))
    finally:
        store.close()


def _print_weekly_summary(config: dict) -> None:
    """Create a store and summary generator, then print this week's summary."""
    db_path = os.path.expanduser(config.get("database_path", "~/.flowtrack/flowtrack.db"))
    store = ActivityStore(db_path)
    store.init_db()
    try:
        poll_interval = config.get("poll_interval_seconds", 5)
        generator = SummaryGenerator(store, poll_interval)
        start_date = date.today() - timedelta(days=date.today().weekday())
        summary = generator.weekly_summary(start_date)
        print(TextFormatter.format_weekly(summary))
    finally:
        store.close()


def main(args: list[str] | None = None) -> None:
    """Entry point for FlowTrack.

    When *args* is ``None`` the arguments are read from ``sys.argv``.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = build_parser()
    parsed = parser.parse_args(args)

    config_path = get_default_config_path()
    config = load_config(str(config_path))

    if parsed.daily:
        _print_daily_summary(config)
    elif parsed.weekly:
        _print_weekly_summary(config)
    else:
        # GUI mode — import here to avoid pulling in pystray/tkinter for CLI usage
        from flowtrack.ui.app import FlowTrackApp

        app = FlowTrackApp(str(config_path))
        app.start()


if __name__ == "__main__":
    main()
