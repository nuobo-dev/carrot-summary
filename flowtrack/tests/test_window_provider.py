"""Unit tests for WindowProvider base class and factory."""

import sys
from unittest.mock import patch, MagicMock

import pytest

from flowtrack.platform.base import WindowProvider
from flowtrack.platform.factory import create_window_provider


class TestWindowProviderABC:
    """Verify the abstract base class cannot be instantiated directly."""

    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            WindowProvider()  # type: ignore[abstract]

    def test_concrete_subclass_can_be_instantiated(self):
        """A subclass implementing all abstract methods should work."""

        class DummyProvider(WindowProvider):
            def get_active_window(self):
                return None

            def is_user_idle(self):
                return False

        provider = DummyProvider()
        assert isinstance(provider, WindowProvider)
        assert provider.get_active_window() is None
        assert provider.is_user_idle() is False


class TestCreateWindowProvider:
    """Tests for the create_window_provider factory function."""

    @patch.object(sys, "platform", "linux")
    def test_unsupported_platform_raises_os_error(self):
        with pytest.raises(OSError, match="Unsupported platform.*linux"):
            create_window_provider()

    @patch.object(sys, "platform", "freebsd")
    def test_another_unsupported_platform_raises(self):
        with pytest.raises(OSError, match="Unsupported platform.*freebsd"):
            create_window_provider()

    def test_darwin_branch_imports_macos_module(self):
        """Verify the darwin branch attempts to import MacOSWindowProvider."""
        mock_cls = MagicMock(spec=WindowProvider)
        mock_module = MagicMock()
        mock_module.MacOSWindowProvider = mock_cls

        with patch.object(sys, "platform", "darwin"), \
             patch.dict("sys.modules", {"flowtrack.platform.macos": mock_module}):
            provider = create_window_provider()
            mock_cls.assert_called_once()
            assert provider is mock_cls.return_value

    def test_win32_branch_imports_windows_module(self):
        """Verify the win32 branch attempts to import WindowsWindowProvider."""
        mock_cls = MagicMock(spec=WindowProvider)
        mock_module = MagicMock()
        mock_module.WindowsWindowProvider = mock_cls

        with patch.object(sys, "platform", "win32"), \
             patch.dict("sys.modules", {"flowtrack.platform.windows": mock_module}):
            provider = create_window_provider()
            mock_cls.assert_called_once()
            assert provider is mock_cls.return_value
