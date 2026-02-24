"""macOS window provider using AppleScript (osascript) and ioreg."""

import logging
import re
import subprocess
from typing import Optional

from flowtrack.core.models import WindowInfo
from flowtrack.platform.base import WindowProvider

logger = logging.getLogger(__name__)

# Default idle threshold in seconds (5 minutes).
_DEFAULT_IDLE_THRESHOLD = 300


class MacOSWindowProvider(WindowProvider):
    """Retrieve active window info and idle state on macOS.

    Uses ``osascript`` to run AppleScript commands for window queries
    and ``ioreg`` to read the HID idle time.
    """

    def __init__(self, idle_threshold: int = _DEFAULT_IDLE_THRESHOLD) -> None:
        self.idle_threshold = idle_threshold

    # ------------------------------------------------------------------
    # WindowProvider interface
    # ------------------------------------------------------------------

    def get_active_window(self) -> Optional[WindowInfo]:
        """Return the frontmost application name and window title.

        Returns ``None`` when the information cannot be retrieved (e.g.
        no windows open, permission denied, or subprocess error).
        """
        app_name = self._get_frontmost_app()
        if app_name is None:
            return None

        window_title = self._get_window_title()
        if window_title is None:
            # Some apps may not expose a window title; use app name.
            window_title = app_name

        return WindowInfo(app_name=app_name, window_title=window_title)

    def is_user_idle(self) -> bool:
        """Return ``True`` when the system idle time exceeds the threshold."""
        idle_seconds = self._get_idle_seconds()
        if idle_seconds is None:
            return False
        return idle_seconds >= self.idle_threshold

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_osascript(self, script: str) -> Optional[str]:
        """Execute an AppleScript snippet via ``osascript`` and return stdout.

        Returns ``None`` on any error.
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.debug(
                    "osascript returned %d: %s", result.returncode, result.stderr.strip()
                )
                return None
            output = result.stdout.strip()
            return output if output else None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("osascript execution failed: %s", exc)
            return None

    def _get_frontmost_app(self) -> Optional[str]:
        """Return the name of the frontmost application process."""
        script = (
            'tell application "System Events" to get name of first '
            "application process whose frontmost is true"
        )
        return self._run_osascript(script)

    def _get_window_title(self) -> Optional[str]:
        """Return the title of the front window of the frontmost app.

        Tries multiple AppleScript approaches since some apps (Electron,
        Chrome) don't expose window names through the standard path.
        """
        # Approach 1: Standard System Events window name
        script1 = (
            'tell application "System Events" to get name of front window '
            "of first application process whose frontmost is true"
        )
        title = self._run_osascript(script1)
        if title:
            return title

        # Approach 2: Get the AXTitle attribute (works for more apps)
        script2 = (
            'tell application "System Events"\n'
            '  set fp to first application process whose frontmost is true\n'
            '  tell fp\n'
            '    set w to first window\n'
            '    return value of attribute "AXTitle" of w\n'
            '  end tell\n'
            'end tell'
        )
        title = self._run_osascript(script2)
        if title:
            return title

        # Approach 3: Ask the app directly for its front window name
        app_name = self._get_frontmost_app()
        if app_name:
            script3 = (
                f'tell application "{app_name}"\n'
                f'  if (count of windows) > 0 then\n'
                f'    return name of front window\n'
                f'  end if\n'
                f'end tell'
            )
            title = self._run_osascript(script3)
            if title:
                return title

        return None

    def _get_idle_seconds(self) -> Optional[float]:
        """Query ``ioreg`` for the HID idle time and return it in seconds.

        The HID idle time is reported in nanoseconds.  Returns ``None``
        when the value cannot be determined.
        """
        try:
            result = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.debug("ioreg returned %d", result.returncode)
                return None

            match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', result.stdout)
            if match is None:
                logger.debug("HIDIdleTime not found in ioreg output")
                return None

            nanoseconds = int(match.group(1))
            return nanoseconds / 1_000_000_000
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("ioreg execution failed: %s", exc)
            return None
