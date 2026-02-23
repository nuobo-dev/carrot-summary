"""Context analyzer for FlowTrack.

Refines a Work_Category into a more specific sub-category by matching
window title patterns. Uses configurable regex rules with named groups
to extract document names and build human-readable context labels.

Falls back to the Work_Category as the sub_category when no rule matches.
"""

import re

from flowtrack.core.models import ContextResult, ContextRule


class ContextAnalyzer:
    """Analyzes window titles to infer specific work context within a category."""

    def __init__(self, rules: list[ContextRule]) -> None:
        self.rules = rules

    def analyze(
        self, app_name: str, window_title: str, category: str
    ) -> ContextResult:
        """Refine a Work_Category into a sub-category based on window title patterns.

        Only rules whose ``category`` matches the input *category* are
        considered.  Rules are evaluated in order; the first matching rule
        wins.  Named regex groups in the matching pattern are used to build
        a human-readable ``context_label``.

        Falls back to *category* as the ``sub_category`` (and
        ``context_label``) when no rule matches.
        """
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

        # No rule matched — fall back to the Work_Category itself.
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
    """Build a human-readable context label from the sub-category and match.

    If the match contains named groups with non-empty values, they are
    joined with ``" "`` and appended to the sub-category after ``": "``.
    Otherwise the label is just the sub-category.
    """
    named = match.groupdict()
    parts = [v.strip() for v in named.values() if v and v.strip()]
    if parts:
        return f"{sub_category}: {' '.join(parts)}"
    return sub_category
