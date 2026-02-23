"""Unit tests for WindowsWindowProvider.

All Win32 API calls are mocked — these tests run on any platform.
We mock the internal helper methods (_get_window_title, _get_app_name)
for get_active_window tests, and mock the DLL calls for idle tests.
"""

from unittest.mock import MagicMock, patch

import pytest

from flowtrack.core.models import WindowInfo
from flowtrack.platform.windows import WindowsWindowProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider(user32=None, kernel32=None, idle_threshold=300):
    """Build a WindowsWindowProvider with injected mock DLLs."""
    with patch.object(WindowsWindowProvider, "__init__", lambda self, **kw: None):
        provider = WindowsWindowProvider()
    provider.idle_threshold = idle_threshold
    provider._user32 = user32 if user32 is not None else MagicMock()
    provider._kernel32 = kernel32 if kernel32 is not None else MagicMock()
    return provider


# ---------------------------------------------------------------------------
# get_active_window
# ---------------------------------------------------------------------------

class TestGetActiveWindow:
    """Tests for WindowsWindowProvider.get_active_window()."""

    def test_returns_window_info_on_success(self):
        """Happy path: both app name and window title are returned."""
        provider = _make_provider()
        provider._user32.GetForegroundWindow.return_value = 12345

        with patch.object(provider, "_get_window_title", return_value="My Document - Notepad"), \
             patch.object(provider, "_get_app_name", return_value="notepad"):
            info = provider.get_active_window()

        assert info is not None
        assert info.app_name == "notepad"
        assert info.window_title == "My Document - Notepad"

    def test_returns_none_when_no_foreground_window(self):
        """If GetForegroundWindow returns 0/NULL, return None."""
        provider = _make_provider()
        provider._user32.GetForegroundWindow.return_value = 0

        assert provider.get_active_window() is None

    def test_returns_none_when_window_title_empty(self):
        """If window title is None, return None."""
        provider = _make_provider()
        provider._user32.GetForegroundWindow.return_value = 12345

        with patch.object(provider, "_get_window_title", return_value=None):
            assert provider.get_active_window() is None

    def test_falls_back_to_title_when_app_name_unavailable(self):
        """If process name lookup fails, use window title as app_name."""
        provider = _make_provider()
        provider._user32.GetForegroundWindow.return_value = 12345

        with patch.object(provider, "_get_window_title", return_value="Untitled - Editor"), \
             patch.object(provider, "_get_app_name", return_value=None):
            info = provider.get_active_window()

        assert info is not None
        assert info.app_name == "Untitled - Editor"
        assert info.window_title == "Untitled - Editor"

    def test_returns_none_when_user32_is_none(self):
        """If Win32 DLLs are unavailable, return None."""
        provider = _make_provider()
        provider._user32 = None
        assert provider.get_active_window() is None

    def test_handles_exception_gracefully(self):
        """Any exception during window retrieval returns None."""
        provider = _make_provider()
        provider._user32.GetForegroundWindow.side_effect = OSError("access denied")

        assert provider.get_active_window() is None


# ---------------------------------------------------------------------------
# _get_window_title (internal helper)
# ---------------------------------------------------------------------------

class TestGetWindowTitle:
    """Tests for the _get_window_title helper."""

    def test_returns_title_on_success(self):
        """GetWindowTextW returns a positive length → title is returned."""
        provider = _make_provider()

        import ctypes
        buf = ctypes.create_unicode_buffer("Hello World", 512)

        with patch("flowtrack.platform.windows.ctypes.create_unicode_buffer", return_value=buf):
            provider._user32.GetWindowTextW.return_value = 11
            result = provider._get_window_title(12345)

        assert result == "Hello World"

    def test_returns_none_on_zero_length(self):
        """GetWindowTextW returns 0 → None."""
        provider = _make_provider()
        provider._user32.GetWindowTextW.return_value = 0

        result = provider._get_window_title(12345)
        assert result is None

    def test_returns_none_on_exception(self):
        """Exception in GetWindowTextW → None."""
        provider = _make_provider()
        provider._user32.GetWindowTextW.side_effect = OSError("fail")

        result = provider._get_window_title(12345)
        assert result is None


# ---------------------------------------------------------------------------
# _get_app_name (internal helper)
# ---------------------------------------------------------------------------

class TestGetAppName:
    """Tests for the _get_app_name helper."""

    def test_returns_none_when_pid_is_zero(self):
        """If GetWindowThreadProcessId sets pid to 0, return None."""
        provider = _make_provider()

        import ctypes.wintypes

        # The real code creates a DWORD and passes byref. We need the mock
        # to leave pid.value at 0 (default).
        with patch("flowtrack.platform.windows.ctypes.wintypes.DWORD") as mock_dword_cls:
            mock_pid = MagicMock()
            mock_pid.value = 0
            mock_dword_cls.return_value = mock_pid

            result = provider._get_app_name(12345)

        assert result is None

    def test_returns_none_when_open_process_fails(self):
        """If OpenProcess returns 0, return None."""
        provider = _make_provider()

        import ctypes.wintypes

        with patch("flowtrack.platform.windows.ctypes.wintypes.DWORD") as mock_dword_cls:
            mock_pid = MagicMock()
            mock_pid.value = 42
            mock_dword_cls.return_value = mock_pid
            provider._kernel32.OpenProcess.return_value = 0

            result = provider._get_app_name(12345)

        assert result is None

    def test_returns_exe_name_stripped(self):
        """Full path with .exe → just the name without extension."""
        provider = _make_provider()

        import ctypes
        import ctypes.wintypes

        # Track DWORD call count to return different objects for pid vs buf_size
        real_dword = ctypes.wintypes.DWORD
        call_count = [0]

        def dword_factory(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: pid DWORD — set value to 42
                d = real_dword(42)
                return d
            return real_dword(*args, **kwargs)

        buf = ctypes.create_unicode_buffer("C:\\Program Files\\notepad.exe", 512)

        with patch("flowtrack.platform.windows.ctypes.wintypes.DWORD", side_effect=dword_factory):
            provider._kernel32.OpenProcess.return_value = 99
            with patch("flowtrack.platform.windows.ctypes.create_unicode_buffer", return_value=buf):
                provider._kernel32.QueryFullProcessImageNameW.return_value = 1
                result = provider._get_app_name(12345)

        assert result == "notepad"
        provider._kernel32.CloseHandle.assert_called_once_with(99)

    def test_returns_name_without_path(self):
        """Executable name without a path separator."""
        provider = _make_provider()

        import ctypes
        import ctypes.wintypes

        real_dword = ctypes.wintypes.DWORD
        call_count = [0]

        def dword_factory(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return real_dword(42)
            return real_dword(*args, **kwargs)

        buf = ctypes.create_unicode_buffer("myapp", 512)

        with patch("flowtrack.platform.windows.ctypes.wintypes.DWORD", side_effect=dword_factory):
            provider._kernel32.OpenProcess.return_value = 99
            with patch("flowtrack.platform.windows.ctypes.create_unicode_buffer", return_value=buf):
                provider._kernel32.QueryFullProcessImageNameW.return_value = 1
                result = provider._get_app_name(12345)

        assert result == "myapp"

    def test_returns_none_on_exception(self):
        """Exception during app name retrieval → None."""
        provider = _make_provider()
        provider._user32.GetWindowThreadProcessId.side_effect = OSError("fail")

        result = provider._get_app_name(12345)
        assert result is None


# ---------------------------------------------------------------------------
# is_user_idle
# ---------------------------------------------------------------------------

class TestIsUserIdle:
    """Tests for WindowsWindowProvider.is_user_idle()."""

    def _setup_idle(self, provider, last_input_time, current_tick,
                    get_last_input_success=True):
        """Configure mocks for idle detection."""
        def fake_get_last_input(lii_ref):
            # lii_ref is a ctypes.byref() wrapper; access the underlying struct.
            lii_ref._obj.dwTime = last_input_time
            return 1 if get_last_input_success else 0

        provider._user32.GetLastInputInfo.side_effect = fake_get_last_input
        provider._kernel32.GetTickCount.return_value = current_tick

    def test_idle_when_above_threshold(self):
        """User is idle when idle time exceeds the threshold."""
        provider = _make_provider(idle_threshold=300)
        # 400 seconds idle: (500000 - 100000) / 1000 = 400
        self._setup_idle(provider, last_input_time=100000, current_tick=500000)

        assert provider.is_user_idle() is True

    def test_not_idle_when_below_threshold(self):
        """User is not idle when idle time is below the threshold."""
        provider = _make_provider(idle_threshold=300)
        # 10 seconds idle: (500000 - 490000) / 1000 = 10
        self._setup_idle(provider, last_input_time=490000, current_tick=500000)

        assert provider.is_user_idle() is False

    def test_idle_at_exact_threshold(self):
        """Exactly at the threshold counts as idle (>=)."""
        provider = _make_provider(idle_threshold=300)
        # 300 seconds idle: (500000 - 200000) / 1000 = 300
        self._setup_idle(provider, last_input_time=200000, current_tick=500000)

        assert provider.is_user_idle() is True

    def test_not_idle_when_user32_is_none(self):
        """If Win32 DLLs are unavailable, return False."""
        provider = _make_provider()
        provider._user32 = None
        assert provider.is_user_idle() is False

    def test_not_idle_when_kernel32_is_none(self):
        """If kernel32 is unavailable, return False."""
        provider = _make_provider()
        provider._kernel32 = None
        assert provider.is_user_idle() is False

    def test_not_idle_when_get_last_input_fails(self):
        """If GetLastInputInfo returns 0, return False."""
        provider = _make_provider()
        self._setup_idle(provider, last_input_time=0, current_tick=500000,
                         get_last_input_success=False)

        assert provider.is_user_idle() is False

    def test_not_idle_on_exception(self):
        """Any exception during idle detection returns False."""
        provider = _make_provider()
        provider._user32.GetLastInputInfo.side_effect = OSError("access denied")

        assert provider.is_user_idle() is False

    def test_custom_idle_threshold(self):
        """Custom threshold should be respected."""
        # 60 seconds idle
        provider_low = _make_provider(idle_threshold=30)
        self._setup_idle(provider_low, last_input_time=440000, current_tick=500000)
        assert provider_low.is_user_idle() is True  # 60s > 30s

        provider_high = _make_provider(idle_threshold=120)
        self._setup_idle(provider_high, last_input_time=440000, current_tick=500000)
        assert provider_high.is_user_idle() is False  # 60s < 120s
