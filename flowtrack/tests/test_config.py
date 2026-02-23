"""Unit tests for the configuration loader."""

import json
import pytest
from pathlib import Path

from flowtrack.core.config import (
    get_data_directory,
    get_default_config,
    get_default_config_path,
    load_config,
    save_config,
)


# ------------------------------------------------------------------
# get_data_directory
# ------------------------------------------------------------------

def test_get_data_directory_returns_path():
    result = get_data_directory()
    assert isinstance(result, Path)
    assert "FlowTrack" in str(result) or ".flowtrack" in str(result)


def test_get_data_directory_macos(monkeypatch):
    monkeypatch.setattr("flowtrack.core.config.sys.platform", "darwin")
    result = get_data_directory()
    assert result == Path.home() / "Library" / "Application Support" / "FlowTrack"


def test_get_data_directory_windows(monkeypatch):
    monkeypatch.setattr("flowtrack.core.config.sys.platform", "win32")
    monkeypatch.setenv("APPDATA", "/fake/appdata")
    result = get_data_directory()
    assert result == Path("/fake/appdata") / "FlowTrack"


def test_get_data_directory_windows_no_appdata(monkeypatch):
    monkeypatch.setattr("flowtrack.core.config.sys.platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    result = get_data_directory()
    assert result == Path.home() / "AppData" / "Roaming" / "FlowTrack"


def test_get_data_directory_linux(monkeypatch):
    monkeypatch.setattr("flowtrack.core.config.sys.platform", "linux")
    result = get_data_directory()
    assert result == Path.home() / ".flowtrack"


# ------------------------------------------------------------------
# get_default_config
# ------------------------------------------------------------------

def test_default_config_has_required_keys():
    cfg = get_default_config()
    assert "poll_interval_seconds" in cfg
    assert "debounce_threshold_seconds" in cfg
    assert "classification_rules" in cfg
    assert "context_rules" in cfg
    assert "pomodoro" in cfg
    assert "report" in cfg
    assert "database_path" in cfg


def test_default_config_pomodoro_values():
    pom = get_default_config()["pomodoro"]
    assert pom["work_minutes"] == 25
    assert pom["short_break_minutes"] == 5
    assert pom["long_break_minutes"] == 15
    assert pom["long_break_interval"] == 4


def test_default_config_classification_rules_non_empty():
    rules = get_default_config()["classification_rules"]
    assert len(rules) > 0
    for rule in rules:
        assert "app_patterns" in rule
        assert "title_patterns" in rule
        assert "category" in rule


# ------------------------------------------------------------------
# save_config / load_config round-trip
# ------------------------------------------------------------------

def test_save_and_load_round_trip(tmp_path):
    cfg_path = tmp_path / "config.json"
    original = get_default_config()
    save_config(original, cfg_path)
    loaded = load_config(cfg_path)
    assert loaded == original


def test_save_creates_parent_directories(tmp_path):
    cfg_path = tmp_path / "nested" / "deep" / "config.json"
    save_config({"key": "value"}, cfg_path)
    assert cfg_path.exists()
    loaded = load_config(cfg_path)
    assert loaded == {"key": "value"}


def test_save_overwrites_existing(tmp_path):
    cfg_path = tmp_path / "config.json"
    save_config({"version": 1}, cfg_path)
    save_config({"version": 2}, cfg_path)
    loaded = load_config(cfg_path)
    assert loaded["version"] == 2


# ------------------------------------------------------------------
# load_config — default creation on first launch
# ------------------------------------------------------------------

def test_load_creates_default_when_missing(tmp_path):
    cfg_path = tmp_path / "config.json"
    assert not cfg_path.exists()
    loaded = load_config(cfg_path)
    assert cfg_path.exists()
    assert loaded == get_default_config()


def test_load_created_default_is_valid_json(tmp_path):
    cfg_path = tmp_path / "config.json"
    load_config(cfg_path)
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict)


# ------------------------------------------------------------------
# load_config — error handling
# ------------------------------------------------------------------

def test_load_invalid_json_returns_defaults(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("not valid json {{{", encoding="utf-8")
    loaded = load_config(cfg_path)
    assert loaded == get_default_config()


def test_load_json_array_returns_defaults(tmp_path):
    """Top-level JSON must be an object, not an array."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("[1, 2, 3]", encoding="utf-8")
    loaded = load_config(cfg_path)
    assert loaded == get_default_config()


def test_load_empty_file_returns_defaults(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("", encoding="utf-8")
    loaded = load_config(cfg_path)
    assert loaded == get_default_config()


# ------------------------------------------------------------------
# load_config — custom values preserved
# ------------------------------------------------------------------

def test_load_preserves_custom_values(tmp_path):
    cfg_path = tmp_path / "config.json"
    custom = {"poll_interval_seconds": 10, "custom_key": "hello"}
    save_config(custom, cfg_path)
    loaded = load_config(cfg_path)
    assert loaded["poll_interval_seconds"] == 10
    assert loaded["custom_key"] == "hello"
