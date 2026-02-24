"""Tests for the CarrotSummary main entry point."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from flowtrack.main import build_parser, main


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_no_args_defaults_to_gui(self):
        parser = build_parser()
        parsed = parser.parse_args([])
        assert parsed.daily is False
        assert parsed.weekly is False

    def test_daily_flag(self):
        parser = build_parser()
        parsed = parser.parse_args(["--daily"])
        assert parsed.daily is True
        assert parsed.weekly is False

    def test_weekly_flag(self):
        parser = build_parser()
        parsed = parser.parse_args(["--weekly"])
        assert parsed.weekly is True
        assert parsed.daily is False

    def test_daily_and_weekly_mutually_exclusive(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--daily", "--weekly"])


class TestMainDaily:
    """Tests for main() in --daily mode."""

    @patch("flowtrack.main._print_daily_summary")
    @patch("flowtrack.main.load_config")
    @patch("flowtrack.main.get_default_config_path")
    def test_daily_calls_print_daily(self, mock_path, mock_load, mock_print):
        mock_path.return_value = "/tmp/config.json"
        mock_load.return_value = {"database_path": ":memory:"}

        main(["--daily"])

        mock_print.assert_called_once_with({"database_path": ":memory:"})

    @patch("flowtrack.main._print_weekly_summary")
    @patch("flowtrack.main.load_config")
    @patch("flowtrack.main.get_default_config_path")
    def test_weekly_calls_print_weekly(self, mock_path, mock_load, mock_print):
        mock_path.return_value = "/tmp/config.json"
        mock_load.return_value = {"database_path": ":memory:"}

        main(["--weekly"])

        mock_print.assert_called_once_with({"database_path": ":memory:"})


class TestMainGUI:
    """Tests for main() in GUI mode (no args)."""

    @patch("flowtrack.ui.app.CarrotSummaryApp", autospec=True)
    @patch("flowtrack.main.load_config")
    @patch("flowtrack.main.get_default_config_path")
    def test_gui_mode_creates_app(self, mock_path, mock_load, MockApp):
        mock_path.return_value = "/tmp/config.json"
        mock_load.return_value = {"database_path": ":memory:"}
        mock_instance = MagicMock()
        MockApp.return_value = mock_instance

        main([])

        MockApp.assert_called_once_with("/tmp/config.json")
        mock_instance.start.assert_called_once()


class TestPrintSummaries:
    """Tests for the summary printing helpers using a real in-memory DB."""

    def test_print_daily_summary_empty_db(self, capsys):
        """Daily summary on an empty database prints without error."""
        from flowtrack.main import _print_daily_summary

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = {"database_path": db_path, "poll_interval_seconds": 5}
            _print_daily_summary(config)

        captured = capsys.readouterr()
        assert "Daily Summary" in captured.out

    def test_print_weekly_summary_empty_db(self, capsys):
        """Weekly summary on an empty database prints without error."""
        from flowtrack.main import _print_weekly_summary

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = {"database_path": db_path, "poll_interval_seconds": 5}
            _print_weekly_summary(config)

        captured = capsys.readouterr()
        assert "Weekly Summary" in captured.out
