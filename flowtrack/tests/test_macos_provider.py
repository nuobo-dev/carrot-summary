"""Unit tests for MacOSWindowProvider.

All subprocess calls are mocked — these tests never invoke osascript or ioreg.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from flowtrack.core.models import WindowInfo
from flowtrack.platform.macos import MacOSWindowProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Build a fake ``subprocess.CompletedProcess``."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# get_active_window
# ---------------------------------------------------------------------------

class TestGetActiveWindow:
    """Tests for MacOSWindowProvider.get_active_window()."""

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_returns_window_info_on_success(self, mock_run):
        """Happy path: both app name and window title are returned."""
        mock_run.side_effect = [
            _completed(stdout="Safari\n"),       # frontmost app
            _completed(stdout="Apple - Start\n"),  # window title
        ]
        provider = MacOSWindowProvider()
        info = provider.get_active_window()

        assert info is not None
        assert info.app_name == "Safari"
        assert info.window_title == "Apple - Start"

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_returns_none_when_app_name_unavailable(self, mock_run):
        """If the frontmost app query fails, return None."""
        mock_run.return_value = _completed(returncode=1, stderr="error")
        provider = MacOSWindowProvider()

        assert provider.get_active_window() is None

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_falls_back_to_app_name_when_title_unavailable(self, mock_run):
        """If all window title approaches fail, use app name as title."""
        mock_run.side_effect = [
            _completed(stdout="Finder\n"),       # _get_frontmost_app
            _completed(returncode=1, stderr="no window"),  # approach 1: System Events window name
            _completed(returncode=1, stderr="no AXTitle"),  # approach 2: AXTitle
            _completed(stdout="Finder\n"),       # approach 3: _get_frontmost_app (for app name)
            _completed(returncode=1, stderr="no window"),  # approach 3: ask app directly
        ]
        provider = MacOSWindowProvider()
        info = provider.get_active_window()

        assert info is not None
        assert info.app_name == "Finder"
        assert info.window_title == "Finder"

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_returns_none_when_app_name_empty(self, mock_run):
        """Empty stdout from osascript should be treated as unavailable."""
        mock_run.return_value = _completed(stdout="")
        provider = MacOSWindowProvider()

        assert provider.get_active_window() is None

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_handles_timeout(self, mock_run):
        """A subprocess timeout should not crash — return None."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=5)
        provider = MacOSWindowProvider()

        assert provider.get_active_window() is None

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_handles_file_not_found(self, mock_run):
        """If osascript binary is missing, return None."""
        mock_run.side_effect = FileNotFoundError("osascript not found")
        provider = MacOSWindowProvider()

        assert provider.get_active_window() is None

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_handles_os_error(self, mock_run):
        """Generic OSError should be handled gracefully."""
        mock_run.side_effect = OSError("permission denied")
        provider = MacOSWindowProvider()

        assert provider.get_active_window() is None


# ---------------------------------------------------------------------------
# is_user_idle
# ---------------------------------------------------------------------------

class TestIsUserIdle:
    """Tests for MacOSWindowProvider.is_user_idle()."""

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_idle_when_above_threshold(self, mock_run):
        """User is idle when HIDIdleTime exceeds the threshold."""
        # 400 seconds in nanoseconds
        ioreg_output = '  |   "HIDIdleTime" = 400000000000\n'
        mock_run.return_value = _completed(stdout=ioreg_output)

        provider = MacOSWindowProvider(idle_threshold=300)
        assert provider.is_user_idle() is True

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_not_idle_when_below_threshold(self, mock_run):
        """User is not idle when HIDIdleTime is below the threshold."""
        # 10 seconds in nanoseconds
        ioreg_output = '  |   "HIDIdleTime" = 10000000000\n'
        mock_run.return_value = _completed(stdout=ioreg_output)

        provider = MacOSWindowProvider(idle_threshold=300)
        assert provider.is_user_idle() is False

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_idle_at_exact_threshold(self, mock_run):
        """Exactly at the threshold counts as idle (>=)."""
        # 300 seconds in nanoseconds
        ioreg_output = '  |   "HIDIdleTime" = 300000000000\n'
        mock_run.return_value = _completed(stdout=ioreg_output)

        provider = MacOSWindowProvider(idle_threshold=300)
        assert provider.is_user_idle() is True

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_not_idle_when_ioreg_fails(self, mock_run):
        """If ioreg fails, assume user is active (return False)."""
        mock_run.return_value = _completed(returncode=1)

        provider = MacOSWindowProvider()
        assert provider.is_user_idle() is False

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_not_idle_when_hid_not_found(self, mock_run):
        """If HIDIdleTime is missing from output, return False."""
        mock_run.return_value = _completed(stdout="some other ioreg output\n")

        provider = MacOSWindowProvider()
        assert provider.is_user_idle() is False

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_not_idle_on_timeout(self, mock_run):
        """Subprocess timeout should not crash — return False."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ioreg", timeout=5)

        provider = MacOSWindowProvider()
        assert provider.is_user_idle() is False

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_not_idle_on_file_not_found(self, mock_run):
        """Missing ioreg binary should not crash — return False."""
        mock_run.side_effect = FileNotFoundError("ioreg not found")

        provider = MacOSWindowProvider()
        assert provider.is_user_idle() is False

    @patch("flowtrack.platform.macos.subprocess.run")
    def test_custom_idle_threshold(self, mock_run):
        """Custom threshold should be respected."""
        # 60 seconds in nanoseconds
        ioreg_output = '  |   "HIDIdleTime" = 60000000000\n'
        mock_run.return_value = _completed(stdout=ioreg_output)

        provider = MacOSWindowProvider(idle_threshold=30)
        assert provider.is_user_idle() is True

        provider2 = MacOSWindowProvider(idle_threshold=120)
        assert provider2.is_user_idle() is False
