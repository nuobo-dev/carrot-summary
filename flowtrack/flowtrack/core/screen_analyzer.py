"""ML-powered screen analysis using macOS Vision framework OCR.

Captures a screenshot on context switches and uses Apple's on-device
Vision framework to extract text, then generates a richer activity
summary than window-title-only analysis.

This is a feature toggle — disabled by default. Enable via config:
  "ml_screen_analysis": true
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class ScreenAnalyzer:
    """Captures and analyzes screen content for richer activity summaries.

    Uses macOS ScreenCaptureKit / CGWindowListCreateImage for screenshots
    and Apple Vision framework for on-device OCR. No data leaves the machine.
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._vision_available = False
        self._capture_available = False
        if enabled:
            self._check_availability()

    def _check_availability(self) -> None:
        """Check if Vision and screen capture APIs are available."""
        try:
            import Quartz  # noqa: F401
            self._capture_available = True
        except ImportError:
            logger.info("Quartz not available — screen capture disabled")

        try:
            import Vision  # noqa: F401
            self._vision_available = True
        except ImportError:
            logger.info("Vision framework not available — OCR disabled")

        if self._capture_available and self._vision_available:
            logger.info("ML screen analysis enabled (Vision OCR + screen capture)")
        else:
            logger.info("ML screen analysis partially available (capture=%s, vision=%s)",
                        self._capture_available, self._vision_available)

    def analyze_screen(self, app_name: str, window_title: str) -> Optional[str]:
        """Capture the screen and return an ML-enhanced activity summary.

        Returns None if disabled, unavailable, or analysis fails.
        The caller should fall back to regex-based summary generation.
        """
        if not self.enabled or not self._capture_available or not self._vision_available:
            return None

        try:
            image = self._capture_screen()
            if image is None:
                return None

            text = self._ocr_image(image)
            if not text:
                return None

            return self._summarize(app_name, window_title, text)
        except Exception:
            logger.debug("Screen analysis failed", exc_info=True)
            return None

    def _capture_screen(self):
        """Capture the current screen as a CGImage."""
        try:
            import Quartz

            # Capture the main display
            image = Quartz.CGWindowListCreateImage(
                Quartz.CGRectInfinite,
                Quartz.kCGWindowListOptionOnScreenOnly,
                Quartz.kCGNullWindowID,
                Quartz.kCGWindowImageDefault,
            )
            return image
        except Exception:
            logger.debug("Screen capture failed", exc_info=True)
            return None

    def _ocr_image(self, cg_image) -> str:
        """Run Vision OCR on a CGImage and return extracted text."""
        try:
            import Vision
            from Foundation import NSArray

            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)

            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
                cg_image, None
            )
            handler.performRequests_error_([request], None)

            results = request.results()
            if not results:
                return ""

            lines = []
            for observation in results:
                candidates = observation.topCandidates_(1)
                if candidates and len(candidates) > 0:
                    lines.append(candidates[0].string())

            return "\n".join(lines)
        except Exception:
            logger.debug("Vision OCR failed", exc_info=True)
            return ""

    def _summarize(self, app_name: str, window_title: str, screen_text: str) -> Optional[str]:
        """Generate a concise activity summary from OCR text.

        Uses heuristic patterns to extract meaningful context from the
        screen content. This is a local, rule-based summarizer — no LLM
        calls, no network requests.
        """
        if not screen_text or len(screen_text) < 10:
            return None

        # Truncate to first ~2000 chars for performance
        text = screen_text[:2000].lower()
        app_lower = app_name.lower() if app_name else ""

        # IDE: look for file tabs, function names, error messages
        if any(k in app_lower for k in ("code", "intellij", "pycharm", "xcode", "vim", "neovim")):
            return self._summarize_ide(screen_text)

        # Browser: look for page content, search queries, form fields
        if any(k in app_lower for k in ("chrome", "firefox", "safari", "edge", "brave", "arc")):
            return self._summarize_browser(screen_text, window_title)

        # Email: look for subject lines, recipients
        if any(k in app_lower for k in ("outlook", "mail", "gmail", "thunderbird")):
            return self._summarize_email(screen_text)

        # Meetings: look for participant names, shared content
        if any(k in app_lower for k in ("zoom", "teams", "meet", "webex")):
            return self._summarize_meeting(screen_text, window_title)

        # Document editors: look for headings, content type
        if any(k in app_lower for k in ("word", "docs", "pages", "notion", "quip")):
            return self._summarize_document(screen_text, window_title)

        return None

    def _summarize_ide(self, text: str) -> Optional[str]:
        """Extract IDE context: current file, errors, test results."""
        lines = text.split("\n")

        # Look for error indicators
        error_count = sum(1 for l in lines if re.search(r'\berror\b', l, re.I))
        if error_count > 0:
            return f"debugging ({error_count} errors visible)"

        # Look for test output
        if any(re.search(r'\b(passed|failed|PASS|FAIL)\b', l) for l in lines):
            return "running/reviewing tests"

        # Look for diff/git indicators
        if any(re.search(r'\b(diff|commit|staged|unstaged)\b', l, re.I) for l in lines):
            return "reviewing code changes"

        return "writing code"

    def _summarize_browser(self, text: str, title: str) -> Optional[str]:
        """Extract browser context from visible page content."""
        text_lower = text.lower()

        # Documentation sites
        if any(k in text_lower for k in ("api reference", "documentation", "docs.", "readme")):
            return f"reading documentation"

        # Stack Overflow / forums
        if any(k in text_lower for k in ("stackoverflow", "stack overflow", "asked", "answered", "votes")):
            return "researching on Stack Overflow"

        # GitHub / code review
        if any(k in text_lower for k in ("pull request", "merge request", "commits", "files changed")):
            return "reviewing code on GitHub"

        # Search
        if any(k in text_lower for k in ("search results", "google.com/search")):
            return "searching the web"

        return None

    def _summarize_email(self, text: str) -> Optional[str]:
        """Extract email context."""
        if re.search(r'\b(compose|new message|reply|forward)\b', text, re.I):
            return "composing email"
        if re.search(r'\b(inbox|all mail|sent)\b', text, re.I):
            return "reading emails"
        return "working in email"

    def _summarize_meeting(self, text: str, title: str) -> Optional[str]:
        """Extract meeting context."""
        # Count visible participant-like names (rough heuristic)
        if re.search(r'\b(screen share|sharing|present)\b', text, re.I):
            return "presenting in meeting"
        if re.search(r'\b(chat|message|send)\b', text, re.I):
            return "chatting in meeting"
        return None

    def _summarize_document(self, text: str, title: str) -> Optional[str]:
        """Extract document editing context."""
        text_lower = text.lower()
        if any(k in text_lower for k in ("table of contents", "heading", "chapter")):
            return "writing document"
        if any(k in text_lower for k in ("comment", "suggestion", "resolve")):
            return "reviewing document comments"
        return "editing document"
