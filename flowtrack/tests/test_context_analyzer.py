"""Unit tests for the ContextAnalyzer."""

import pytest

from flowtrack.core.models import ContextResult, ContextRule
from flowtrack.core.context_analyzer import ContextAnalyzer


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_rules() -> list[ContextRule]:
    """Return a small set of context rules for testing."""
    return [
        ContextRule(
            category="Document Editing",
            title_patterns=[r"(?i)(?P<doc>contract|agreement|nda)"],
            sub_category="Contract Draft",
        ),
        ContextRule(
            category="Document Editing",
            title_patterns=[r"(?i)(?P<doc>meeting.*notes|minutes)"],
            sub_category="Meeting Notes",
        ),
        ContextRule(
            category="Document Editing",
            title_patterns=[r"(?i)(?P<doc>design|spec|proposal)"],
            sub_category="Design Brief",
        ),
        ContextRule(
            category="Research & Browsing",
            title_patterns=[r"(?i)(?P<site>jira|trello|asana)"],
            sub_category="Project Management",
        ),
    ]


# ------------------------------------------------------------------
# analyze — basic rule matching
# ------------------------------------------------------------------

def test_matches_contract_rule():
    analyzer = ContextAnalyzer(_make_rules())
    result = analyzer.analyze("Microsoft Word", "Contract Draft - Smith v. Jones", "Document Editing")
    assert result.category == "Document Editing"
    assert result.sub_category == "Contract Draft"
    assert "Contract" in result.context_label


def test_matches_meeting_notes_rule():
    analyzer = ContextAnalyzer(_make_rules())
    result = analyzer.analyze("Google Docs", "Weekly Meeting Notes - Q4", "Document Editing")
    assert result.sub_category == "Meeting Notes"


def test_matches_design_brief_rule():
    analyzer = ContextAnalyzer(_make_rules())
    result = analyzer.analyze("Pages", "Design Doc v2", "Document Editing")
    assert result.sub_category == "Design Brief"


def test_matches_browser_project_management():
    analyzer = ContextAnalyzer(_make_rules())
    result = analyzer.analyze("Chrome", "Jira - Sprint Board", "Research & Browsing")
    assert result.sub_category == "Project Management"


# ------------------------------------------------------------------
# analyze — fallback behavior
# ------------------------------------------------------------------

def test_fallback_when_no_rule_matches():
    """When no context rule matches but title has content, use cleaned title."""
    analyzer = ContextAnalyzer(_make_rules())
    result = analyzer.analyze("Notepad", "random file.txt", "Document Editing")
    assert result.category == "Document Editing"
    # The smart parser or clean title extraction should produce something meaningful
    assert result.sub_category != ""
    assert len(result.sub_category) > 0


def test_fallback_when_category_has_no_rules():
    """A category with zero matching rules uses cleaned title or falls back."""
    analyzer = ContextAnalyzer(_make_rules())
    result = analyzer.analyze("Zoom", "Standup Call", "Meetings")
    # Should extract "Standup Call" from the title rather than just "Meetings"
    assert result.sub_category in ("Standup Call", "Meetings", "Meeting: Standup Call")
    assert len(result.context_label) > 0


def test_fallback_with_empty_rules():
    analyzer = ContextAnalyzer([])
    result = analyzer.analyze("Chrome", "Google", "Research & Browsing")
    assert result.sub_category == "Research & Browsing"
    assert result.context_label == "Research & Browsing"


def test_fallback_with_empty_strings():
    analyzer = ContextAnalyzer(_make_rules())
    result = analyzer.analyze("", "", "Other")
    assert result.sub_category == "Other"
    assert result.context_label == "Other"


# ------------------------------------------------------------------
# analyze — only rules for the matching category are considered
# ------------------------------------------------------------------

def test_only_matching_category_rules_apply():
    """A Document Editing rule should NOT match when category is Research & Browsing."""
    analyzer = ContextAnalyzer(_make_rules())
    # "contract" appears in title but category is Research & Browsing
    result = analyzer.analyze("Chrome", "contract law overview", "Research & Browsing")
    # Should NOT match the Contract Draft rule (that's for Document Editing)
    assert result.sub_category != "Contract Draft"


# ------------------------------------------------------------------
# analyze — first matching rule wins
# ------------------------------------------------------------------

def test_first_matching_rule_wins():
    rules = [
        ContextRule(
            category="Dev",
            title_patterns=[r"(?i)python"],
            sub_category="Python Dev",
        ),
        ContextRule(
            category="Dev",
            title_patterns=[r"(?i)python"],
            sub_category="Scripting",
        ),
    ]
    analyzer = ContextAnalyzer(rules)
    result = analyzer.analyze("VSCode", "main.python project", "Dev")
    assert result.sub_category == "Python Dev"


# ------------------------------------------------------------------
# analyze — named group extraction and context_label
# ------------------------------------------------------------------

def test_named_group_in_context_label():
    """Named groups from the regex should appear in the context_label."""
    rules = [
        ContextRule(
            category="Document Editing",
            title_patterns=[r"(?P<name>.+)\s*-\s*Microsoft Word"],
            sub_category="Word Document",
        ),
    ]
    analyzer = ContextAnalyzer(rules)
    result = analyzer.analyze("Microsoft Word", "Smith v. Jones - Microsoft Word", "Document Editing")
    assert result.sub_category == "Word Document"
    assert "Word Document:" in result.context_label
    assert "Smith v. Jones" in result.context_label


def test_multiple_named_groups():
    rules = [
        ContextRule(
            category="Development",
            title_patterns=[r"(?P<project>\w+)\s*-\s*(?P<file>\w+\.py)"],
            sub_category="Python File",
        ),
    ]
    analyzer = ContextAnalyzer(rules)
    result = analyzer.analyze("VSCode", "CarrotSummary - main.py", "Development")
    assert result.sub_category == "Python File"
    assert "Python File:" in result.context_label
    assert "CarrotSummary" in result.context_label
    assert "main.py" in result.context_label


def test_no_named_groups_label_is_sub_category():
    """When the pattern has no named groups, the label is just the sub_category."""
    rules = [
        ContextRule(
            category="Email",
            title_patterns=[r"(?i)inbox"],
            sub_category="Email Inbox",
        ),
    ]
    analyzer = ContextAnalyzer(rules)
    result = analyzer.analyze("Outlook", "Inbox - Outlook", "Email")
    assert result.sub_category == "Email Inbox"
    assert result.context_label == "Email Inbox"


# ------------------------------------------------------------------
# analyze — case insensitivity via regex flags
# ------------------------------------------------------------------

def test_case_insensitive_matching():
    analyzer = ContextAnalyzer(_make_rules())
    result = analyzer.analyze("Word", "NDA DOCUMENT", "Document Editing")
    assert result.sub_category == "Contract Draft"


# ------------------------------------------------------------------
# analyze — invalid regex patterns are skipped
# ------------------------------------------------------------------

def test_invalid_regex_skipped():
    rules = [
        ContextRule(
            category="Dev",
            title_patterns=["[invalid"],  # bad regex
            sub_category="Bad Rule",
        ),
        ContextRule(
            category="Dev",
            title_patterns=[r"(?i)python"],
            sub_category="Python Dev",
        ),
    ]
    analyzer = ContextAnalyzer(rules)
    result = analyzer.analyze("VSCode", "python project", "Dev")
    assert result.sub_category == "Python Dev"


# ------------------------------------------------------------------
# analyze — multiple title patterns in a single rule
# ------------------------------------------------------------------

def test_multiple_title_patterns_first_match_wins():
    rules = [
        ContextRule(
            category="Document Editing",
            title_patterns=[r"(?i)report", r"(?i)summary"],
            sub_category="Status Report",
        ),
    ]
    analyzer = ContextAnalyzer(rules)
    # "report" matches first pattern
    r1 = analyzer.analyze("Word", "Quarterly Report", "Document Editing")
    assert r1.sub_category == "Status Report"
    # "summary" matches second pattern
    r2 = analyzer.analyze("Word", "Weekly Summary", "Document Editing")
    assert r2.sub_category == "Status Report"
