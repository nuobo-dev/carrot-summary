"""Configuration loader for CarrotSummary.

Handles loading, saving, and default creation of config.json.
Resolves platform-appropriate data directories:
  - macOS:   ~/Library/Application Support/CarrotSummary
  - Windows: %APPDATA%/CarrotSummary
  - Other:   ~/.carrotsummary
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_data_directory() -> Path:
    """Return the platform-appropriate data directory for CarrotSummary."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        base = Path.home()
        return base / ".carrotsummary"
    return base / "CarrotSummary"


def get_default_config() -> dict[str, Any]:
    """Return the default configuration dictionary."""
    data_dir = get_data_directory()
    return {
        "poll_interval_seconds": 5,
        "debounce_threshold_seconds": 30,
        "classification_rules": [
            {
                "app_patterns": ["Microsoft Word", "Google Docs", "Pages", "Quip", "Notion", "Obsidian", "Bear"],
                "title_patterns": [r"(?i)\.docx?\b", r"(?i)\.md\b"],
                "category": "Document Editing",
            },
            {
                "app_patterns": ["Outlook", "Gmail", "Thunderbird", "Mail"],
                "title_patterns": [r"(?i)\binbox\b", r"(?i)\bcompose\b", r"(?i)\breply\b"],
                "category": "Email & Communication",
            },
            {
                "app_patterns": ["Slack", "Discord", "Microsoft Teams", "Messages"],
                "title_patterns": [],
                "category": "Email & Communication",
            },
            {
                "app_patterns": ["Zoom", "Teams", "Webex", "Google Meet", "FaceTime"],
                "title_patterns": [r"(?i)\bmeeting\b", r"(?i)\bcall\b"],
                "category": "Meetings",
            },
            {
                "app_patterns": ["Microsoft Excel", "Google Sheets", "Numbers"],
                "title_patterns": [r"(?i)\.xlsx?\b"],
                "category": "Spreadsheets",
            },
            {
                "app_patterns": ["Microsoft PowerPoint", "Google Slides", "Keynote"],
                "title_patterns": [r"(?i)\.pptx?\b"],
                "category": "Presentations",
            },
            {
                "app_patterns": ["Jira", "Asana", "Trello", "Linear", "Monday", "ClickUp", "Taskei"],
                "title_patterns": [],
                "category": "Project Management",
            },
            {
                "app_patterns": ["Figma", "Sketch", "Adobe Photoshop", "Adobe Illustrator", "Canva"],
                "title_patterns": [],
                "category": "Creative Tools",
            },
            {
                "app_patterns": ["Visual Studio Code", "Code", "IntelliJ", "PyCharm", "WebStorm", "Xcode", "Sublime Text", "Vim", "Neovim"],
                "title_patterns": [],
                "category": "Development",
            },
            {
                "app_patterns": ["Terminal", "iTerm2", "iTerm", "Warp", "Alacritty", "Hyper"],
                "title_patterns": [],
                "category": "Development",
            },
            {
                "app_patterns": ["Chrome", "Firefox", "Safari", "Edge", "Brave", "Arc", "Opera"],
                "title_patterns": [".*"],
                "category": "Research & Browsing",
            },
        ],
        "context_rules": [
            {
                "category": "Document Editing",
                "title_patterns": ["(?i)contract|agreement|nda"],
                "sub_category": "Contract Draft",
            },
            {
                "category": "Document Editing",
                "title_patterns": ["(?i)meeting.*notes|minutes"],
                "sub_category": "Meeting Notes",
            },
            {
                "category": "Document Editing",
                "title_patterns": ["(?i)design|spec|proposal"],
                "sub_category": "Design Brief",
            },
        ],
        "pomodoro": {
            "work_minutes": 25,
            "short_break_minutes": 5,
            "long_break_minutes": 15,
            "long_break_interval": 4,
        },
        "report": {
            "user_name": "",
            "output_directory": "~/flowtrack-reports",
            "email": {
                "to_address": "",
                "smtp_server": "",
                "smtp_port": 587,
                "smtp_username": "",
                "smtp_password": "",
                "use_tls": True,
            },
        },
        "database_path": str(data_dir / "carrotsummary.db"),
    }


def get_default_config_path() -> Path:
    """Return the default path for config.json."""
    return get_data_directory() / "config.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from a JSON file.

    If *path* is ``None``, the platform default location is used.
    When the file does not exist, a default configuration is created,
    written to disk, and returned.  If the file exists but is invalid
    JSON, the error is logged and defaults are returned.
    """
    config_path = Path(path) if path is not None else get_default_config_path()

    if not config_path.exists():
        logger.info("Config file not found at %s — creating defaults.", config_path)
        defaults = get_default_config()
        save_config(defaults, config_path)
        return defaults

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("Top-level JSON value must be an object")
        return data
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.error("Failed to load config from %s: %s — using defaults.", config_path, exc)
        return get_default_config()


def save_config(config: dict[str, Any], path: str | Path | None = None) -> None:
    """Write *config* to a JSON file.

    If *path* is ``None``, the platform default location is used.
    Parent directories are created automatically.
    """
    config_path = Path(path) if path is not None else get_default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
