"""Activity classifier for CarrotSummary.

Maps application names and window titles to Work_Categories using
configurable regex-based rules. Rules are evaluated in order; the
first matching rule wins. Returns "Other" when no rule matches.
"""

import json
import re
from pathlib import Path

from flowtrack.core.models import ClassificationRule


class Classifier:
    """Classifies window activity into Work_Categories using regex rules."""

    def __init__(self, rules: list[ClassificationRule]) -> None:
        self.rules = rules

    def classify(self, app_name: str, window_title: str) -> str:
        """Return the Work_Category for the given app and title.

        Rules are evaluated in order. A rule matches if ANY of its
        app_patterns match the app_name OR ANY of its title_patterns
        match the window_title (using ``re.search``).

        Returns ``"Other"`` if no rule matches.
        """
        for rule in self.rules:
            if _rule_matches(rule, app_name, window_title):
                return rule.category
        return "Other"

    @staticmethod
    def load_rules(path: str) -> list[ClassificationRule]:
        """Deserialize classification rules from a JSON file.

        The file must contain a JSON array of objects, each with keys
        ``app_patterns``, ``title_patterns``, and ``category``.
        """
        file_path = Path(path)
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [
            ClassificationRule(
                app_patterns=entry["app_patterns"],
                title_patterns=entry["title_patterns"],
                category=entry["category"],
            )
            for entry in data
        ]

    @staticmethod
    def save_rules(rules: list[ClassificationRule], path: str) -> None:
        """Serialize classification rules to a JSON file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "app_patterns": rule.app_patterns,
                "title_patterns": rule.title_patterns,
                "category": rule.category,
            }
            for rule in rules
        ]
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)


def _rule_matches(
    rule: ClassificationRule, app_name: str, window_title: str
) -> bool:
    """Return True if the rule matches the given app name or window title."""
    for pattern in rule.app_patterns:
        try:
            if re.search(pattern, app_name):
                return True
        except re.error:
            continue
    for pattern in rule.title_patterns:
        try:
            if re.search(pattern, window_title):
                return True
        except re.error:
            continue
    return False
