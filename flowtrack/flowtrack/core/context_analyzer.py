"""Context analyzer for CarrotSummary.

Refines a Work_Category into a specific sub-category by:
1. Matching configurable regex rules with named groups
2. Smart title parsing that extracts document names, email subjects,
   project names, etc. from common window title patterns

Falls back to the Work_Category as the sub_category when nothing matches.
"""

import re
from typing import Optional

from flowtrack.core.models import ContextResult, ContextRule


# Common suffixes/noise to strip from window titles
_STRIP_SUFFIXES = [
    r"\s*[-–—]\s*(Google Chrome|Firefox|Safari|Microsoft Edge|Brave|Arc|Opera)$",
    r"\s*[-–—]\s*(Microsoft Word|Microsoft Excel|Microsoft PowerPoint)$",
    r"\s*[-–—]\s*(Google Docs|Google Sheets|Google Slides)$",
    r"\s*[-–—]\s*(Pages|Numbers|Keynote)$",
    r"\s*[-–—]\s*(Visual Studio Code|VS Code|Code)$",
    r"\s*[-–—]\s*(Sublime Text|Atom|Vim|Neovim|Emacs)$",
    r"\s*[-–—]\s*(Slack|Discord|Microsoft Teams)$",
    r"\s*[-–—]\s*(Outlook|Mail|Thunderbird)$",
    r"\s*[-–—]\s*(Figma|Sketch|Adobe \w+)$",
    r"\s*[-–—]\s*(Notion|Obsidian|Bear|Evernote)$",
    r"\s*[-–—]\s*(Terminal|iTerm2?|Warp|Alacritty|Hyper)$",
    r"\s*[-–—]\s*(Quip|Confluence|Coda)$",
]

# Labels that are too generic to be useful as task names
_GENERIC_LABELS = {
    "new tab", "untitled", "google", "search", "home", "about:blank",
    "loading", "gmail", "inbox", "mail", "outlook", "calendar",
    "google chrome", "firefox", "safari", "edge", "brave", "arc",
    "electron", "code", "terminal", "finder", "desktop",
}

# Patterns for extracting granular context from window titles
_SMART_PATTERNS: list[tuple[str, str, list[str]]] = [
    # Email: "Subject - recipient@email.com - Outlook"
    ("Email & Communication", "Emailing: {subject}",
     [r"(?i)(?:re:\s*|fw:\s*|fwd:\s*)*(?P<subject>.+?)\s*[-–—]\s*(?P<recipient>[^-–—]+@[^-–—]+)",
      r"(?i)(?:compose|new message|reply|forward).*?(?:to|:)\s*(?P<recipient>[^-–—]+)",
      r"(?i)(?:re:\s*|fw:\s*|fwd:\s*)*(?P<subject>.+?)(?:\s*[-–—]|$)"]),

    # Email inbox/reading
    ("Email & Communication", "Reading emails",
     [r"(?i)^(inbox|mail|all mail|sent|drafts|spam|trash|junk)\b"]),

    # Meetings with title
    ("Meetings", "Meeting: {subject}",
     [r"(?i)(?P<subject>.+?)\s*[-–—]\s*(?:zoom|teams|webex|google meet|meet)",
      r"(?i)(?:zoom|teams|webex|meet)\s*[-–—]\s*(?P<subject>.+)"]),

    # Google Docs / Quip / Notion — document title is usually the first part
    ("Document Editing", "Writing: {doc}",
     [r"(?P<doc>.+?)\s*[-–—]\s*(?:Google Docs|Quip|Notion|Pages)",
      r"(?P<doc>.+?)\s*[-–—]\s*(?:Microsoft Word|Word)",
      r"(?P<doc>.+?)\.docx?\b",
      r"(?P<doc>.+?)\.md\b"]),

    # Spreadsheets
    ("Spreadsheets", "Spreadsheet: {doc}",
     [r"(?P<doc>.+?)\s*[-–—]\s*(?:Google Sheets|Microsoft Excel|Numbers)",
      r"(?P<doc>.+?)\.xlsx?\b"]),

    # Presentations
    ("Presentations", "Presentation: {doc}",
     [r"(?P<doc>.+?)\s*[-–—]\s*(?:Google Slides|Microsoft PowerPoint|Keynote)",
      r"(?P<doc>.+?)\.pptx?\b"]),

    # IDE / Development — extract filename or project
    ("Development", "Coding: {file}",
     [r"(?P<file>[^\s]+\.\w{1,5})\s*[-–—]\s*(?P<project>.+)",
      r"(?P<project>.+?)\s*[-–—]\s*(?:Visual Studio|VS Code|Code|IntelliJ|PyCharm|WebStorm)"]),

    # Browser tabs — extract the page title
    ("Research & Browsing", "Browsing: {page}",
     [r"(?P<page>.+?)\s*[-–—]\s*(?:Google Chrome|Firefox|Safari|Edge|Brave|Arc)"]),

    # Slack/Teams channels
    ("Email & Communication", "Chat: {channel}",
     [r"(?P<channel>.+?)\s*[-–—]\s*(?:Slack|Discord)",
      r"(?i)(?:slack|discord)\s*[-–—]\s*(?P<channel>.+)"]),

    # Project management tools
    ("Project Management", "Task: {item}",
     [r"(?P<item>.+?)\s*[-–—]\s*(?:Jira|Asana|Trello|Linear|Monday|ClickUp|Taskei)",
      r"(?i)(?:jira|asana|trello|linear)\s*[-–—]\s*(?P<item>.+)"]),

    # Design tools
    ("Creative Tools", "Designing: {file}",
     [r"(?P<file>.+?)\s*[-–—]\s*(?:Figma|Sketch|Adobe \w+|Canva)"]),
]


class ContextAnalyzer:
    """Analyzes window titles to infer specific work context within a category."""

    def __init__(self, rules: list[ContextRule]) -> None:
        self.rules = rules

    def analyze(
        self, app_name: str, window_title: str, category: str
    ) -> ContextResult:
        """Refine a Work_Category into a sub-category based on window title.

        Priority:
        1. User-configured rules (exact match by category)
        2. Smart title parsing (built-in patterns)
        3. Clean title extraction (strip app name suffix)
        4. Fall back to category name
        """
        # 1. Try user-configured rules first
        for rule in self.rules:
            if rule.category != category:
                continue
            match = _match_title(rule.title_patterns, window_title)
            if match is not None:
                label = _build_label(rule.sub_category, match)
                return ContextResult(
                    category=category,
                    sub_category=rule.sub_category,
                    context_label=label,
                )

        # 2. Try smart title parsing
        result = _smart_parse(window_title, category)
        if result is not None:
            return result

        # 3. Try to extract a clean title by stripping app name
        clean = _clean_title(window_title)
        if clean and clean.lower() not in _GENERIC_LABELS and clean.lower() != category.lower() and len(clean) > 4:
            return ContextResult(
                category=category,
                sub_category=clean,
                context_label=clean,
            )

        # 4. Fall back to category
        return ContextResult(
            category=category,
            sub_category=category,
            context_label=category,
        )


def _match_title(
    patterns: list[str], window_title: str
) -> "re.Match[str] | None":
    """Return the first successful match against *window_title*, or None."""
    for pattern in patterns:
        try:
            m = re.search(pattern, window_title)
            if m is not None:
                return m
        except re.error:
            continue
    return None


def _build_label(sub_category: str, match: "re.Match[str]") -> str:
    """Build a human-readable context label from the sub-category and match."""
    named = match.groupdict()
    parts = [v.strip() for v in named.values() if v and v.strip()]
    if parts:
        return f"{sub_category}: {' '.join(parts)}"
    return sub_category


def _smart_parse(window_title: str, category: str) -> Optional[ContextResult]:
    """Try built-in smart patterns to extract granular context."""
    for pat_category, label_template, patterns in _SMART_PATTERNS:
        if pat_category != category:
            continue
        for pattern in patterns:
            try:
                m = re.search(pattern, window_title)
                if m is None:
                    continue
                groups = m.groupdict()
                # Build the sub_category from the template
                sub = label_template
                for key, val in groups.items():
                    if val:
                        val = val.strip().rstrip(" -–—")
                        sub = sub.replace(f"{{{key}}}", val)
                # Remove unfilled placeholders
                sub = re.sub(r"\{[^}]+\}", "", sub).strip(": ")
                if not sub or len(sub) < 3:
                    continue
                # Skip generic/unhelpful labels
                if sub.lower().strip() in _GENERIC_LABELS:
                    continue
                # Truncate very long labels
                if len(sub) > 80:
                    sub = sub[:77] + "..."
                return ContextResult(
                    category=category,
                    sub_category=sub,
                    context_label=sub,
                )
            except re.error:
                continue
    return None


def _clean_title(window_title: str) -> str:
    """Strip common app name suffixes from a window title."""
    cleaned = window_title
    for pattern in _STRIP_SUFFIXES:
        try:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        except re.error:
            continue
    return cleaned.strip(" -–—")
