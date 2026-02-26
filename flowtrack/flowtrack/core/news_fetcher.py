"""AI news fetcher using web search and RSS feeds.

Fetches top AI news from reliable sources, caches results for 1 hour.
Two modes: business-focused (non-technical) and technical (open source, new tech).
"""

import json
import logging
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

# Cache: {news_type: (timestamp, items)}
_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # 1 hour

# RSS feeds for AI news
_BUSINESS_FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Reuters Tech", "https://www.rss-bridge.org/bridge01/?action=display&bridge=FilterBridge&url=https%3A%2F%2Fwww.reuters.com%2Ftechnology%2Frss&filter=AI+OR+artificial+intelligence&filter_type=permit&format=Atom"),
    ("Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
]

_TECHNICAL_FEEDS = [
    ("Hacker News", "https://hnrss.org/newest?q=AI+OR+LLM+OR+machine+learning&points=50"),
    ("arXiv AI", "https://rss.arxiv.org/rss/cs.AI"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("GitHub Trending", "https://mshibanami.github.io/GitHubTrendingRSS/daily/python.xml"),
    ("MIT Tech Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
]


def fetch_ai_news(news_type: str = "business", max_items: int = 10) -> list[dict]:
    """Fetch AI news items. Returns cached results if available."""
    # Check cache
    if news_type in _cache:
        cached_time, cached_items = _cache[news_type]
        if time.time() - cached_time < _CACHE_TTL:
            return cached_items

    all_items = []

    # Primary: web search for recent AI news
    search_items = _search_web_news(news_type)
    all_items.extend(search_items)

    # Secondary: RSS feeds
    feeds = _BUSINESS_FEEDS if news_type == "business" else _TECHNICAL_FEEDS
    for source_name, feed_url in feeds:
        try:
            items = _parse_feed(feed_url, source_name)
            all_items.extend(items)
        except Exception:
            logger.debug("Failed to fetch feed: %s", source_name, exc_info=True)

    # Strictly filter to last 7 days only
    cutoff = datetime.now() - timedelta(days=7)
    recent = [i for i in all_items if i.get("published_dt") and i["published_dt"] > cutoff]

    # For items without a parsed date, include them if they came from web search
    # (web search results are inherently recent)
    no_date = [i for i in all_items if not i.get("published_dt") and i.get("from_search")]
    recent.extend(no_date)

    # Sort by date descending (undated items go to the end)
    recent.sort(key=lambda x: x.get("published_dt") or datetime.min, reverse=True)

    # Take top N and format, deduplicating
    result = []
    seen_titles = set()
    for item in recent:
        norm = re.sub(r'\s+', ' ', item.get("title", "").lower().strip())
        if norm in seen_titles or len(norm) < 10:
            continue
        seen_titles.add(norm)

        formatted = _format_item(item, news_type)
        result.append(formatted)
        if len(result) >= max_items:
            break

    # Cache results
    _cache[news_type] = (time.time(), result)
    return result


def _search_web_news(news_type: str) -> list[dict]:
    """Use web search to find recent AI news."""
    if news_type == "business":
        queries = [
            "top AI news this week 2026",
            "artificial intelligence business news last 7 days",
        ]
    else:
        queries = [
            "new AI open source projects this week 2026",
            "latest AI ML technical news last 7 days",
        ]

    items = []
    for query in queries:
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
            parsed = _parse_feed(url, "Google News")
            for item in parsed:
                item["from_search"] = True
            items.extend(parsed)
        except Exception:
            logger.debug("Web search failed for: %s", query, exc_info=True)

    return items


def _parse_feed(url: str, source_name: str) -> list[dict]:
    """Parse an RSS/Atom feed and return raw items."""
    req = urllib.request.Request(url, headers={"User-Agent": "CarrotSummary/2.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = resp.read()

    root = ElementTree.fromstring(data)
    items = []

    # Try RSS 2.0 format
    for item in root.iter("item"):
        title = _get_text(item, "title")
        link = _get_text(item, "link")
        desc = _get_text(item, "description")
        pub_date = _get_text(item, "pubDate")
        items.append({
            "title": _clean_html(title or ""),
            "link": link or "",
            "description": _clean_html(desc or ""),
            "published": pub_date or "",
            "published_dt": _parse_date(pub_date),
            "source": source_name,
        })

    # Try Atom format
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = _get_text(entry, "{http://www.w3.org/2005/Atom}title")
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.get("href", "") if link_el is not None else ""
        summary = _get_text(entry, "{http://www.w3.org/2005/Atom}summary") or _get_text(entry, "{http://www.w3.org/2005/Atom}content")
        updated = _get_text(entry, "{http://www.w3.org/2005/Atom}updated") or _get_text(entry, "{http://www.w3.org/2005/Atom}published")
        items.append({
            "title": _clean_html(title or ""),
            "link": link,
            "description": _clean_html(summary or ""),
            "published": updated or "",
            "published_dt": _parse_date(updated),
            "source": source_name,
        })

    return items


def _format_item(item: dict, news_type: str) -> dict:
    """Format a news item for display."""
    title = item.get("title", "")
    desc = item.get("description", "")
    source = item.get("source", "")
    link = item.get("link", "")
    pub_dt = item.get("published_dt")

    # Format date
    date_str = ""
    if pub_dt:
        date_str = pub_dt.strftime("%B %d, %Y")

    # Create headline — concise summary that captures the full picture
    headline = _make_headline(title, desc)

    # Create takeaway from description (2-3 sentences)
    takeaway = _extract_takeaway(desc, title)

    # Create relevance note
    if news_type == "business":
        relevance = _business_relevance(title, desc)
    else:
        relevance = _technical_relevance(title, desc)

    return {
        "headline": headline,
        "takeaway": takeaway,
        "relevance": relevance,
        "source": source,
        "link": link,
        "date": date_str,
        "type": news_type,
    }


def _make_headline(title: str, desc: str) -> str:
    """Create a concise, complete headline from the title.

    Instead of truncating at 10 words (which cuts off meaning), this:
    1. Strips source attribution suffixes (e.g., "- TechCrunch")
    2. Removes filler words to compress
    3. Keeps the full meaning intact
    """
    if not title:
        return "AI News Update"

    # Strip common source suffixes: "Title - Source Name"
    cleaned = re.sub(r'\s*[-–—|]\s*(TechCrunch|The Verge|Reuters|WSJ|Ars Technica|'
                     r'VentureBeat|MIT Technology Review|Wired|CNBC|Bloomberg|'
                     r'The New York Times|BBC|CNN|Google News|Hacker News|'
                     r'The Guardian|Forbes|Business Insider|ZDNet|Engadget|'
                     r'The Information|Axios|Protocol|Semafor|Rest of World)\s*$',
                     '', title, flags=re.IGNORECASE).strip()

    # Strip leading "AI:" or "Artificial Intelligence:" prefixes
    cleaned = re.sub(r'^(?:AI|Artificial Intelligence)\s*[:–—]\s*', '', cleaned, flags=re.IGNORECASE).strip()

    # If it's already short enough (under ~80 chars), use as-is
    if len(cleaned) <= 80:
        return cleaned

    # Compress: remove filler phrases
    compressed = cleaned
    fillers = [
        r'\baccording to\b.*?(?=,|$)', r'\breport says\b', r'\breports say\b',
        r'\bin a move that\b', r'\bin what could be\b', r'\bit was announced that\b',
        r'\bthe company said\b', r'\bthe company announced\b',
    ]
    for filler in fillers:
        compressed = re.sub(filler, '', compressed, flags=re.IGNORECASE).strip()
    compressed = re.sub(r'\s{2,}', ' ', compressed).strip(' ,;:')

    # If still too long, take up to the first natural break (comma, colon, dash)
    if len(compressed) > 80:
        for sep in [': ', ' — ', ' – ', ', ']:
            idx = compressed.find(sep)
            if 20 < idx < 75:
                compressed = compressed[:idx]
                break

    # Final fallback: just cap at 80 chars on a word boundary
    if len(compressed) > 80:
        compressed = compressed[:77].rsplit(' ', 1)[0] + '...'

    return compressed


def _extract_takeaway(desc: str, title: str = "") -> str:
    """Extract 2-3 sentence takeaway from description."""
    if not desc:
        if title:
            return title
        return "Details available at the source link."
    # Split into sentences and take first 2-3
    sentences = re.split(r'(?<=[.!?])\s+', desc.strip())
    sentences = [s for s in sentences if len(s) > 20]
    return " ".join(sentences[:3]) if sentences else desc[:300]


def _business_relevance(title: str, desc: str) -> str:
    """Generate a business-relevance note."""
    text = (title + " " + desc).lower()
    if any(k in text for k in ("enterprise", "business", "company", "revenue", "market")):
        return "Directly impacts enterprise AI adoption and business strategy."
    if any(k in text for k in ("regulation", "policy", "government", "law")):
        return "May affect AI governance and compliance requirements at work."
    if any(k in text for k in ("productivity", "automation", "workflow", "tool")):
        return "Could change how teams work and automate daily tasks."
    if any(k in text for k in ("launch", "release", "announce", "new")):
        return "New capability that could be relevant to your team's projects."
    return "Relevant to staying informed about the evolving AI landscape."


def _technical_relevance(title: str, desc: str) -> str:
    """Generate a technical-relevance note."""
    text = (title + " " + desc).lower()
    if any(k in text for k in ("open source", "github", "repository", "library")):
        return "Open source project worth evaluating for your tech stack."
    if any(k in text for k in ("benchmark", "performance", "faster", "efficient")):
        return "Performance improvement that could benefit your infrastructure."
    if any(k in text for k in ("model", "llm", "transformer", "training")):
        return "Advances in model architecture relevant to ML engineering."
    if any(k in text for k in ("api", "sdk", "framework", "tool")):
        return "New developer tooling that could accelerate your workflow."
    return "Technical development worth tracking for engineering decisions."


def _get_text(element, tag: str) -> Optional[str]:
    """Get text content of a child element."""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _clean_html(text: str) -> str:
    """Strip HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text).strip()


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Try to parse various date formats from RSS feeds."""
    if not date_str:
        return None
    # Common RSS date formats
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",      # RFC 822
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",            # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            continue
    return None
