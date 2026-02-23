"""Tests for SettingsWindow (non-GUI structural tests).

These tests verify config handling, construction, and save logic
without requiring a display or running the tkinter event loop.
"""

import json
import sys
import types
import pytest
from unittest.mock import MagicMock, patch

# Provide stub tkinter modules so the settings module can be imported
# even when _tkinter (the C extension) is not available.
_tk_stub = types.ModuleType("tkinter")
_tk_stub.Toplevel = MagicMock
_tk_stub.BooleanVar = MagicMock
_ttk_stub = types.ModuleType("tkinter.ttk")
_ttk_stub.Style = MagicMock
_ttk_stub.Notebook = MagicMock
_ttk_stub.Frame = MagicMock
_ttk_stub.Label = MagicMock
_ttk_stub.Entry = MagicMock
_ttk_stub.Button = MagicMock
_ttk_stub.Checkbutton = MagicMock
_ttk_stub.Spinbox = MagicMock
_ttk_stub.Treeview = MagicMock
_ttk_stub.Scrollbar = MagicMock
_msgbox_stub = types.ModuleType("tkinter.messagebox")
_msgbox_stub.showinfo = MagicMock()
_msgbox_stub.showwarning = MagicMock()
_msgbox_stub.showerror = MagicMock()

# Only patch if tkinter is not genuinely available
if "_tkinter" not in sys.modules:
    sys.modules.setdefault("tkinter", _tk_stub)
    sys.modules.setdefault("tkinter.ttk", _ttk_stub)
    sys.modules.setdefault("tkinter.messagebox", _msgbox_stub)

from flowtrack.core.config import get_default_config
from flowtrack.ui.settings import SettingsWindow, _deep_copy_dict


class TestDeepCopyDict:
    """Test the helper deep-copy function."""

    def test_returns_equal_dict(self):
        original = {"a": 1, "b": [2, 3], "c": {"d": 4}}
        copied = _deep_copy_dict(original)
        assert copied == original

    def test_mutation_does_not_affect_original(self):
        original = {"nested": {"key": "value"}, "list": [1, 2]}
        copied = _deep_copy_dict(original)
        copied["nested"]["key"] = "changed"
        copied["list"].append(3)
        assert original["nested"]["key"] == "value"
        assert original["list"] == [1, 2]


class TestSettingsWindowInit:
    """Test SettingsWindow construction without showing the window."""

    def test_stores_config_copy(self):
        config = get_default_config()
        callback = MagicMock()
        sw = SettingsWindow(config, callback)
        # Config should be a deep copy, not the same object
        assert sw.config == config
        assert sw.config is not config

    def test_stores_on_save_callback(self):
        callback = MagicMock()
        sw = SettingsWindow({}, callback)
        assert sw.on_save is callback

    def test_window_initially_none(self):
        sw = SettingsWindow({}, MagicMock())
        assert sw._window is None


class TestSettingsWindowSave:
    """Test the _save method by mocking tkinter widgets."""

    def _create_window_with_mocked_widgets(self, config=None):
        """Create a SettingsWindow and mock all widget attributes."""
        if config is None:
            config = get_default_config()
        callback = MagicMock()
        sw = SettingsWindow(config, callback)

        # Mock the window so destroy() works
        sw._window = MagicMock()

        # Mock email widgets
        sw._smtp_server = MagicMock()
        sw._smtp_server.get.return_value = "smtp.example.com"
        sw._smtp_port = MagicMock()
        sw._smtp_port.get.return_value = "587"
        sw._smtp_username = MagicMock()
        sw._smtp_username.get.return_value = "user@example.com"
        sw._smtp_password = MagicMock()
        sw._smtp_password.get.return_value = "secret"
        sw._use_tls = MagicMock()
        sw._use_tls.get.return_value = True
        sw._to_address = MagicMock()
        sw._to_address.get.return_value = "recipient@example.com"

        # Mock category/context rule lists
        sw._cat_rules = [
            {"category": "Dev", "app_patterns": ["VSCode"], "title_patterns": []},
        ]
        sw._ctx_rules = [
            {"category": "Dev", "title_patterns": ["(?i)readme"], "sub_category": "Docs"},
        ]

        # Mock pomodoro widgets
        sw._work_min = MagicMock()
        sw._work_min.get.return_value = "25"
        sw._short_break = MagicMock()
        sw._short_break.get.return_value = "5"
        sw._long_break = MagicMock()
        sw._long_break.get.return_value = "15"
        sw._long_interval = MagicMock()
        sw._long_interval.get.return_value = "4"
        sw._debounce = MagicMock()
        sw._debounce.get.return_value = "30"

        return sw, callback

    def test_save_calls_on_save_with_updated_config(self):
        sw, callback = self._create_window_with_mocked_widgets()
        sw._save()

        callback.assert_called_once()
        saved = callback.call_args[0][0]

        # Email settings
        email = saved["report"]["email"]
        assert email["smtp_server"] == "smtp.example.com"
        assert email["smtp_port"] == 587
        assert email["smtp_username"] == "user@example.com"
        assert email["smtp_password"] == "secret"
        assert email["use_tls"] is True
        assert email["to_address"] == "recipient@example.com"

        # Classification rules
        assert len(saved["classification_rules"]) == 1
        assert saved["classification_rules"][0]["category"] == "Dev"

        # Context rules
        assert len(saved["context_rules"]) == 1
        assert saved["context_rules"][0]["sub_category"] == "Docs"

        # Pomodoro
        assert saved["pomodoro"]["work_minutes"] == 25
        assert saved["pomodoro"]["short_break_minutes"] == 5
        assert saved["pomodoro"]["long_break_minutes"] == 15
        assert saved["pomodoro"]["long_break_interval"] == 4
        assert saved["debounce_threshold_seconds"] == 30

    def test_save_destroys_window(self):
        sw, _ = self._create_window_with_mocked_widgets()
        sw._save()
        sw._window.destroy.assert_called_once()

    @patch("flowtrack.ui.settings.messagebox")
    def test_save_rejects_invalid_port(self, mock_msgbox):
        sw, callback = self._create_window_with_mocked_widgets()
        sw._smtp_port.get.return_value = "not_a_number"
        sw._save()
        callback.assert_not_called()
        mock_msgbox.showerror.assert_called_once()

    @patch("flowtrack.ui.settings.messagebox")
    def test_save_rejects_invalid_pomodoro_values(self, mock_msgbox):
        sw, callback = self._create_window_with_mocked_widgets()
        sw._work_min.get.return_value = "abc"
        sw._save()
        callback.assert_not_called()
        mock_msgbox.showerror.assert_called_once()

    def test_save_preserves_existing_config_keys(self):
        config = get_default_config()
        config["database_path"] = "/custom/path.db"
        sw, callback = self._create_window_with_mocked_widgets(config)
        sw._save()
        saved = callback.call_args[0][0]
        assert saved["database_path"] == "/custom/path.db"
