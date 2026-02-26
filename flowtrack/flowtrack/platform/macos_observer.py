"""Event-driven macOS window observer using NSWorkspace notifications.

Replaces polling with native macOS notifications for app activation
and window title changes. Falls back to periodic title checks for
apps that don't emit AXTitleChanged (like browsers switching tabs).
"""

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from flowtrack.core.models import WindowInfo
from flowtrack.platform.macos import MacOSWindowProvider

logger = logging.getLogger(__name__)


class MacOSWindowObserver:
    """Observes window changes via NSWorkspace notifications + lightweight title polling.

    Instead of polling every 5s for the full window info, this observer:
    1. Listens for NSWorkspace.didActivateApplicationNotification (app switches)
    2. Runs a lightweight title-only check every few seconds to catch tab/document changes
    3. Only fires the callback when something actually changed

    This dramatically reduces subprocess calls (no osascript every 5s when nothing changes).
    """

    def __init__(
        self,
        provider: MacOSWindowProvider,
        on_change: Callable[[WindowInfo, datetime], None],
        title_check_interval: float = 3.0,
    ) -> None:
        self._provider = provider
        self._on_change = on_change
        self._title_check_interval = title_check_interval
        self._running = False
        self._last_app: Optional[str] = None
        self._last_title: Optional[str] = None
        self._observer_thread: Optional[threading.Thread] = None
        self._ns_observer = None

    def start(self) -> None:
        """Start observing window changes."""
        self._running = True

        # Try to set up NSWorkspace notification observer
        if self._setup_ns_observer():
            logger.info("Using NSWorkspace notifications for app switch detection")
        else:
            logger.info("NSWorkspace notifications unavailable, using title polling only")

        # Start the title-check thread (catches tab switches, document changes)
        self._observer_thread = threading.Thread(
            target=self._title_check_loop, daemon=True, name="flowtrack-title-observer"
        )
        self._observer_thread.start()

    def stop(self) -> None:
        """Stop observing."""
        self._running = False
        self._teardown_ns_observer()
        if self._observer_thread is not None:
            self._observer_thread.join(timeout=5)
            self._observer_thread = None

    def _setup_ns_observer(self) -> bool:
        """Set up NSWorkspace didActivateApplication notification."""
        try:
            from AppKit import NSWorkspace, NSRunLoop, NSDefaultRunLoopMode
            from Foundation import NSObject
            import objc

            # Create a delegate class that handles the notification
            class _AppSwitchHandler(NSObject):
                observer_ref = None

                def appDidActivate_(self, notification):
                    if self.observer_ref:
                        self.observer_ref._handle_app_switch()

            handler = _AppSwitchHandler.alloc().init()
            handler.observer_ref = self

            ws = NSWorkspace.sharedWorkspace()
            nc = ws.notificationCenter()
            nc.addObserver_selector_name_object_(
                handler,
                objc.selector(handler.appDidActivate_, signature=b"v@:@"),
                "NSWorkspaceDidActivateApplicationNotification",
                None,
            )
            self._ns_observer = handler
            self._ns_notification_center = nc

            # Run the notification center processing in a background thread
            def _run_loop():
                from AppKit import NSRunLoop, NSDefaultRunLoopMode, NSDate
                while self._running:
                    NSRunLoop.currentRunLoop().runMode_beforeDate_(
                        NSDefaultRunLoopMode,
                        NSDate.dateWithTimeIntervalSinceNow_(0.5),
                    )

            t = threading.Thread(target=_run_loop, daemon=True, name="flowtrack-nsrunloop")
            t.start()
            return True

        except ImportError:
            logger.debug("AppKit/pyobjc not available for NSWorkspace notifications")
            return False
        except Exception:
            logger.debug("Failed to set up NSWorkspace observer", exc_info=True)
            return False

    def _teardown_ns_observer(self) -> None:
        """Remove the NSWorkspace notification observer."""
        if self._ns_observer is not None:
            try:
                self._ns_notification_center.removeObserver_(self._ns_observer)
            except Exception:
                pass
            self._ns_observer = None

    def _handle_app_switch(self) -> None:
        """Called when NSWorkspace detects an app activation."""
        try:
            self._check_and_fire()
        except Exception:
            logger.debug("Error handling app switch notification", exc_info=True)

    def _title_check_loop(self) -> None:
        """Periodically check if the window title changed (catches tab switches)."""
        while self._running:
            try:
                if not self._provider.is_user_idle():
                    self._check_and_fire()
            except Exception:
                logger.debug("Error in title check loop", exc_info=True)
            time.sleep(self._title_check_interval)

    def _check_and_fire(self) -> None:
        """Check current window and fire callback if it changed."""
        try:
            info = self._provider.get_active_window()
        except Exception:
            return

        if info is None:
            return

        # Only fire if something actually changed
        if info.app_name == self._last_app and info.window_title == self._last_title:
            return

        self._last_app = info.app_name
        self._last_title = info.window_title
        now = datetime.now()

        try:
            self._on_change(info, now)
        except Exception:
            logger.exception("Error in window change callback")
