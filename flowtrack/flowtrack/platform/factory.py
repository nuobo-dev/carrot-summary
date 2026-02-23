"""Factory for creating the appropriate WindowProvider for the current OS."""

import sys

from flowtrack.platform.base import WindowProvider


def create_window_provider() -> WindowProvider:
    """Detect the current OS and return the matching WindowProvider.

    Uses lazy imports so platform-specific modules are only loaded on
    the OS where they are actually needed.

    Returns:
        A concrete WindowProvider for the current platform.

    Raises:
        OSError: If the current platform is not supported.
    """
    if sys.platform == "darwin":
        from flowtrack.platform.macos import MacOSWindowProvider
        return MacOSWindowProvider()

    if sys.platform == "win32":
        from flowtrack.platform.windows import WindowsWindowProvider
        return WindowsWindowProvider()

    raise OSError(
        f"Unsupported platform: {sys.platform!r}. "
        "FlowTrack supports macOS (darwin) and Windows (win32)."
    )
