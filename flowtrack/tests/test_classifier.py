"""Unit tests for the Classifier."""

import json
import pytest

from flowtrack.core.models import ClassificationRule
from flowtrack.core.classifier import Classifier


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_rules() -> list[ClassificationRule]:
    """Return a small set of rules for testing."""
    return [
        ClassificationRule(
            app_patterns=["Microsoft Word", "Google Docs"],
            title_patterns=[],
            category="Document Editing",
        ),
        ClassificationRule(
            app_patterns=["Outlook", "Gmail"],
            title_patterns=[],
            category="Email & Communication",
        ),
        ClassificationRule(
            app_patterns=[],
            title_patterns=[r"(?i)zoom|teams|webex"],
            category="Meetings",
        ),
        ClassificationRule(
            app_patterns=["Chrome", "Firefox"],
            title_patterns=[],
            category="Research & Browsing",
        ),
    ]


# ------------------------------------------------------------------
# classify — basic matching
# ------------------------------------------------------------------

def test_classify_matches_app_pattern():
    c = Classifier(_make_rules())
    assert c.classify("Microsoft Word", "Report.docx") == "Document Editing"


def test_classify_matches_title_pattern():
    c = Classifier(_make_rules())
    assert c.classify("SomeApp", "Zoom Meeting - Standup") == "Meetings"


def test_classify_returns_other_when_no_match():
    c = Classifier(_make_rules())
    assert c.classify("UnknownApp", "random window") == "Other"


def test_classify_empty_strings_return_other():
    c = Classifier(_make_rules())
    assert c.classify("", "") == "Other"


def test_classify_no_rules_returns_other():
    c = Classifier([])
    assert c.classify("Chrome", "Google") == "Other"


# ------------------------------------------------------------------
# classify — first-match-wins ordering
# ------------------------------------------------------------------

def test_classify_first_matching_rule_wins():
    rules = [
        ClassificationRule(app_patterns=["Chrome"], title_patterns=[], category="Browsing"),
        ClassificationRule(app_patterns=["Chrome"], title_patterns=[], category="Social Media"),
    ]
    c = Classifier(rules)
    assert c.classify("Chrome", "Twitter") == "Browsing"


# ------------------------------------------------------------------
# classify — regex behavior
# ------------------------------------------------------------------

def test_classify_regex_partial_match():
    """re.search matches anywhere in the string, not just the start."""
    rules = [
        ClassificationRule(app_patterns=["Word"], title_patterns=[], category="Docs"),
    ]
    c = Classifier(rules)
    assert c.classify("Microsoft Word 365", "file.docx") == "Docs"


def test_classify_case_insensitive_title_pattern():
    rules = [
        ClassificationRule(
            app_patterns=[],
            title_patterns=[r"(?i)meeting"],
            category="Meetings",
        ),
    ]
    c = Classifier(rules)
    assert c.classify("App", "MEETING NOTES") == "Meetings"
    assert c.classify("App", "meeting notes") == "Meetings"


def test_classify_invalid_regex_skipped():
    """A rule with an invalid regex pattern should not crash; it just won't match."""
    rules = [
        ClassificationRule(
            app_patterns=["[invalid"],  # bad regex
            title_patterns=[],
            category="Bad",
        ),
        ClassificationRule(
            app_patterns=["Chrome"],
            title_patterns=[],
            category="Browsing",
        ),
    ]
    c = Classifier(rules)
    assert c.classify("Chrome", "page") == "Browsing"


def test_classify_app_or_title_either_matches():
    """A rule matches if ANY app_pattern OR ANY title_pattern matches."""
    rules = [
        ClassificationRule(
            app_patterns=["VSCode"],
            title_patterns=[r"\.py$"],
            category="Development",
        ),
    ]
    c = Classifier(rules)
    # matches via app_pattern
    assert c.classify("VSCode", "readme.md") == "Development"
    # matches via title_pattern
    assert c.classify("SomeEditor", "main.py") == "Development"


# ------------------------------------------------------------------
# load_rules / save_rules — JSON round-trip
# ------------------------------------------------------------------

def test_save_and_load_round_trip(tmp_path):
    rules = _make_rules()
    path = str(tmp_path / "rules.json")
    Classifier.save_rules(rules, path)
    loaded = Classifier.load_rules(path)
    assert loaded == rules


def test_save_creates_parent_dirs(tmp_path):
    path = str(tmp_path / "nested" / "deep" / "rules.json")
    Classifier.save_rules(_make_rules(), path)
    loaded = Classifier.load_rules(path)
    assert len(loaded) == len(_make_rules())


def test_save_produces_valid_json(tmp_path):
    path = tmp_path / "rules.json"
    Classifier.save_rules(_make_rules(), str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    for entry in data:
        assert "app_patterns" in entry
        assert "title_patterns" in entry
        assert "category" in entry


def test_load_empty_list(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text("[]", encoding="utf-8")
    loaded = Classifier.load_rules(str(path))
    assert loaded == []


def test_round_trip_preserves_empty_patterns(tmp_path):
    rules = [
        ClassificationRule(app_patterns=[], title_patterns=[], category="Empty"),
    ]
    path = str(tmp_path / "rules.json")
    Classifier.save_rules(rules, path)
    loaded = Classifier.load_rules(path)
    assert loaded == rules
