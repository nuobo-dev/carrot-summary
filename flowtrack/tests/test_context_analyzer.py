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


# ------------------------------------------------------------------
# analyze — activity_summary generation
# ------------------------------------------------------------------

class TestActivitySummary:
    """Tests for the activity_summary field generated by analyze()."""

    def setup_method(self):
        self.analyzer = ContextAnalyzer(_make_rules())

    # -- Smart pattern: IDE file editing --
    def test_summary_ide_file_editing(self):
        result = self.analyzer.analyze("VS Code", "models.py - FlowTrack", "Development")
        assert result.activity_summary == "edited models.py"

    # -- Smart pattern: document editing in Word --
    def test_summary_document_editing_word(self):
        result = self.analyzer.analyze("Microsoft Word", "Design Spec - Microsoft Word", "Document Editing")
        assert result.activity_summary == "edited Design Spec"

    # -- Smart pattern: document with version --
    def test_summary_document_with_version(self):
        result = self.analyzer.analyze("Google Docs", "design spec v2 - Google Docs", "Document Editing")
        assert result.activity_summary == "edited design spec v2"

    # -- Smart pattern: pull request review --
    def test_summary_pull_request(self):
        result = self.analyzer.analyze("Chrome", "Pull Request #42 - GitHub - Google Chrome", "Research & Browsing")
        assert result.activity_summary == "reviewed pull request #42"

    # -- Smart pattern: browser research --
    def test_summary_browser_research(self):
        result = self.analyzer.analyze("Google Chrome", "Stack Overflow - Google Chrome", "Research & Browsing")
        assert result.activity_summary == "researched Stack Overflow"

    # -- Smart pattern: meeting --
    def test_summary_meeting(self):
        result = self.analyzer.analyze("Zoom", "Sprint Planning - Zoom", "Meetings")
        assert result.activity_summary == "attended Sprint Planning"

    def test_summary_zoom_meeting_with_title(self):
        """Zoom Meeting - Subject extracts the meeting title."""
        result = self.analyzer.analyze("zoom.us", "Zoom Meeting - Sprint Planning", "Meetings")
        assert result.activity_summary == "attended Sprint Planning"

    def test_summary_zoom_meeting_title_before_dash(self):
        """Subject - Zoom Meeting extracts the meeting title."""
        result = self.analyzer.analyze("zoom.us", "Design Review - Zoom Meeting", "Meetings")
        assert result.activity_summary == "attended Design Review"

    def test_summary_zoom_meeting_bare(self):
        """Plain 'Zoom Meeting' with no title gives generic summary."""
        result = self.analyzer.analyze("zoom.us", "Zoom Meeting", "Meetings")
        assert result.activity_summary == "attended Zoom meeting"

    # -- Smart pattern: Slack channel --
    def test_summary_slack_channel(self):
        result = self.analyzer.analyze("Slack", "team-engineering - Slack", "Email & Communication")
        assert result.activity_summary == "chatted in team-engineering"

    # -- Smart pattern: email --
    def test_summary_email(self):
        result = self.analyzer.analyze("Outlook", "Re: Project Update - Outlook", "Email & Communication")
        assert result.activity_summary == "emailed about Project Update"

    # -- Smart pattern: spreadsheet --
    def test_summary_spreadsheet(self):
        result = self.analyzer.analyze("Excel", "Budget 2024 - Microsoft Excel", "Spreadsheets")
        assert result.activity_summary == "edited spreadsheet Budget 2024"

    # -- Smart pattern: presentation --
    def test_summary_presentation(self):
        result = self.analyzer.analyze("PowerPoint", "Q4 Review - Microsoft PowerPoint", "Presentations")
        assert result.activity_summary == "edited presentation Q4 Review"

    # -- Smart pattern: project management --
    def test_summary_project_management(self):
        result = self.analyzer.analyze("Chrome", "FLOW-123 Fix login bug - Jira", "Project Management")
        assert result.activity_summary == "managed task FLOW-123 Fix login bug"

    # -- Smart pattern: design tool --
    def test_summary_design_tool(self):
        result = self.analyzer.analyze("Figma", "Dashboard Mockup - Figma", "Creative Tools")
        assert result.activity_summary == "designed Dashboard Mockup"

    # -- Smart pattern: ticket with ID --
    def test_summary_ticket_id(self):
        result = self.analyzer.analyze("Chrome", "AUTH-456: authentication issue - Portal", "Research & Browsing")
        assert "AUTH-456" in result.activity_summary
        assert "authentication issue" in result.activity_summary

    # -- Fallback: app_name: cleaned_title --
    def test_summary_fallback_app_and_title(self):
        result = self.analyzer.analyze("CustomApp", "Some Unique Window", "Other")
        assert result.activity_summary == "CustomApp: Some Unique Window"

    # -- Fallback: empty inputs --
    def test_summary_empty_inputs(self):
        result = self.analyzer.analyze("", "", "Other")
        assert result.activity_summary == "Other"

    # -- Fallback: generic title --
    def test_summary_generic_title_uses_app(self):
        result = self.analyzer.analyze("Chrome", "New Tab", "Research & Browsing")
        # "New Tab" is generic, should fall back
        assert result.activity_summary != ""

    # -- Summary is always non-empty --
    def test_summary_always_non_empty(self):
        result = self.analyzer.analyze("SomeApp", "SomeTitle", "Other")
        assert result.activity_summary != ""
        assert len(result.activity_summary) > 0

    # -- Summary is set on all code paths --
    def test_summary_set_on_rule_match(self):
        """When a user-configured rule matches, summary should still be set."""
        result = self.analyzer.analyze("Microsoft Word", "Contract Draft - Smith v. Jones", "Document Editing")
        assert result.activity_summary != ""

    def test_summary_set_on_smart_parse(self):
        """When smart parse matches, summary should be set."""
        result = self.analyzer.analyze("Chrome", "Stack Overflow - Google Chrome", "Research & Browsing")
        assert result.activity_summary != ""

    def test_summary_set_on_clean_title_fallback(self):
        """When clean title extraction is used, summary should be set."""
        result = self.analyzer.analyze("Notepad", "my_notes.txt", "Document Editing")
        assert result.activity_summary != ""

    def test_summary_set_on_category_fallback(self):
        """When falling back to category, summary should be set."""
        analyzer = ContextAnalyzer([])
        result = analyzer.analyze("Chrome", "Google", "Research & Browsing")
        assert result.activity_summary != ""

    # -- Terminal commands --
    def test_summary_terminal(self):
        result = self.analyzer.analyze("Terminal", "~/projects - Terminal", "Development")
        assert "ran commands" in result.activity_summary

    # -- Truncation for very long titles --
    def test_summary_truncation(self):
        long_title = "A" * 200 + " - Google Chrome"
        result = self.analyzer.analyze("Chrome", long_title, "Research & Browsing")
        assert len(result.activity_summary) <= 103  # 100 + "..."
