"""Windows window provider using ctypes with user32.dll and kernel32.dll."""

import ctypes
import ctypes.wintypes
import logging
from typing import Optional

from flowtrack.core.models import WindowInfo
from flowtrack.platform.base import WindowProvider

logger = logging.getLogger(__name__)

# Default idle threshold in seconds (5 minutes).
_DEFAULT_IDLE_THRESHOLD = 300

# Buffer size for window title retrieval.
_TITLE_BUFFER_SIZE = 512


class LASTINPUTINFO(ctypes.Structure):
    """Win32 LASTINPUTINFO structure for idle detection."""
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


class WindowsWindowProvider(WindowProvider):
    """Retrieve active window info and idle state on Windows.

    Uses ``ctypes`` with ``user32.dll`` for window queries and
    ``GetLastInputInfo`` / ``GetTickCount`` for idle detection.
    """

    def __init__(self, idle_threshold: int = _DEFAULT_IDLE_THRESHOLD) -> None:
        self.idle_threshold = idle_threshold
        try:
            self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            self._kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        except (AttributeError, OSError) as exc:
            logger.warning("Win32 DLLs unavailable: %s", exc)
            self._user32 = None
            self._kernel32 = None

    # ------------------------------------------------------------------
    # WindowProvider interface
    # ------------------------------------------------------------------

    def get_active_window(self) -> Optional[WindowInfo]:
        """Return the foreground window's app name and title.

        Returns ``None`` when the information cannot be retrieved.
        """
        if self._user32 is None:
            return None

        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return None

            window_title = self._get_window_title(hwnd)
            if not window_title:
                return None

            app_name = self._get_app_name(hwnd)
            if not app_name:
                app_name = window_title

            return WindowInfo(app_name=app_name, window_title=window_title)
        except Exception as exc:
            logger.debug("Failed to get active window: %s", exc)
            return None

    def is_user_idle(self) -> bool:
        """Return ``True`` when the system idle time exceeds the threshold."""
        if self._user32 is None or self._kernel32 is None:
            return False

        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)

            if not self._user32.GetLastInputInfo(ctypes.byref(lii)):
                logger.debug("GetLastInputInfo failed")
                return False

            current_tick = self._kernel32.GetTickCount()
            idle_ms = current_tick - lii.dwTime

            # Handle tick count wraparound (occurs every ~49.7 days).
            if idle_ms < 0:
                idle_ms += 0xFFFFFFFF + 1

            idle_seconds = idle_ms / 1000.0
            return idle_seconds >= self.idle_threshold
        except (OSError, Exception) as exc:
            logger.debug("Idle detection failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_window_title(self, hwnd: int) -> Optional[str]:
        """Retrieve the title of the given window handle."""
        try:
            buf = ctypes.create_unicode_buffer(_TITLE_BUFFER_SIZE)
            length = self._user32.GetWindowTextW(hwnd, buf, _TITLE_BUFFER_SIZE)
            if length > 0:
                return buf.value
            return None
        except (OSError, Exception) as exc:
            logger.debug("GetWindowTextW failed: %s", exc)
            return None

    def _get_app_name(self, hwnd: int) -> Optional[str]:
        """Retrieve the executable name for the process owning the window."""
        try:
            pid = ctypes.wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == 0:
                return None

            # Use kernel32 OpenProcess + GetModuleFileNameExW via psapi.
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = self._kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
            )
            if not handle:
                return None

            try:
                buf = ctypes.create_unicode_buffer(_TITLE_BUFFER_SIZE)
                # QueryFullProcessImageNameW is available on Vista+.
                buf_size = ctypes.wintypes.DWORD(_TITLE_BUFFER_SIZE)
                success = self._kernel32.QueryFullProcessImageNameW(
                    handle, 0, buf, ctypes.byref(buf_size)
                )
                if success and buf.value:
                    # Extract just the filename from the full path.
                    path = buf.value
                    # Use rfind to get the last path separator.
                    sep_idx = max(path.rfind("\\"), path.rfind("/"))
                    name = path[sep_idx + 1:] if sep_idx >= 0 else path
                    # Strip .exe extension for cleaner display.
                    if name.lower().endswith(".exe"):
                        name = name[:-4]
                    return name
                return None
            finally:
                self._kernel32.CloseHandle(handle)
        except (OSError, Exception) as exc:
            logger.debug("Failed to get app name: %s", exc)
            return None
