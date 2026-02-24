"""Abstract base class for platform-specific window providers."""

from abc import ABC, abstractmethod
from typing import Optional

from flowtrack.core.models import WindowInfo


class WindowProvider(ABC):
    """Common interface for retrieving active window information.

    Each supported platform (macOS, Windows) provides a concrete
    implementation that uses OS-specific APIs behind this interface.
    """

    @abstractmethod
    def get_active_window(self) -> Optional[WindowInfo]:
        """Return the currently active window info, or None if unavailable."""
        pass

    @abstractmethod
    def is_user_idle(self) -> bool:
        """Return True if the screen is locked or system is idle."""
        pass
