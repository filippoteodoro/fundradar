"""
Diff engine for detecting meaningful changes between snapshots.

Compares text content and identifies what changed, filtering out noise.
Also provides specialized parsing for news/press pages to extract individual items.

Sprint 2 enhancement: Integrates with normalizer.py for noise-resistant diffing.
Phase 2 enhancement: Integrates with site_extractor.py for site-specific extraction.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import TypedDict

from bs4 import BeautifulSoup


def _normalize_signal_title(title: str, max_len: int = 200) -> str:
    """Normalize whitespace and truncate at word boundary."""
    title = re.sub(r'\s+', ' ', title).strip()
    if len(title) <= max_len:
        return title
    truncated = title[:max_len].rsplit(' ', 1)[0]
    return truncated


# Import site-specific extractor (lazy to avoid circular imports)
def _get_site_extractor():
    from .site_extractor import extract_news_items as site_extract_news_items
    return site_extract_news_items


# Lazy import normalizer to avoid circular imports
def _get_normalizer():
    from .normalizer import ContentNormalizer
    return ContentNormalizer()


class NewsItem(TypedDict):
    """A news/press item extracted from a page."""
    title: str
    date: str | None  # Normalized date string YYYY-MM-DD or raw if unparsable
    url: str | None   # Link to the full article
    fingerprint: str  # Hash for change detection


@dataclass
class NewsPageResult:
    """Result of parsing a news/press page."""
    items: list[NewsItem]
    new_items: list[NewsItem]  # Items not in previous snapshot
    changed_items: list[NewsItem]  # Items with updated content


@dataclass
class DiffResult:
    """Result of comparing two snapshots."""

    has_changes: bool
    is_meaningful: bool
    change_ratio: float  # 0.0 to 1.0
    added_lines: list[str]
    removed_lines: list[str]
    summary: str


# Patterns to filter out as noise (dates, counters, etc.)
NOISE_PATTERNS = [
    r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}$",  # Dates
    r"^\d{1,2}:\d{2}(:\d{2})?$",  # Times
    r"^©\s*\d{4}",  # Copyright years
    r"^\d+\s*(views?|clicks?|likes?|shares?|comments?)$",  # Counters
    r"^(cookie|privacy|terms)",  # Legal boilerplate
    r"^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d",
    r"^\d+$",  # Standalone numbers (counters, IDs)
    r"^(accept|reject|close|dismiss|ok|cancel|submit)$",  # Button labels
    r"utm_",  # Tracking params
    r"^\s*$",  # Empty/whitespace only
]

# Additional patterns for high-value page noise filtering
HIGH_VALUE_NOISE_PATTERNS = [
    r"cookie",
    r"privacy policy",
    r"terms of service",
    r"terms and conditions",
    r"accept all",
    r"reject all",
    r"manage preferences",
    r"subscribe",
    r"newsletter",
    r"follow us",
    r"share on",
    r"linkedin",
    r"twitter",
    r"facebook",
    r"loading",
    r"please wait",
    r"copyright",
    r"all rights reserved",
    r"©",
]

# Minimum thresholds for meaningful changes
MIN_CHANGE_RATIO = 0.01  # At least 1% of content changed
MIN_ADDED_CHARS = 50  # At least 50 chars of new content
MIN_MEANINGFUL_LINES = 2  # At least 2 meaningful lines changed


def is_noise_line(line: str, strict: bool = False) -> bool:
    """
    Check if a line is likely noise (dates, counters, boilerplate).

    Args:
        line: The line to check
        strict: If True, use stricter filtering for high-value pages
    """
    line_lower = line.lower().strip()

    if len(line_lower) < 5:  # Very short lines are usually noise
        return True

    for pattern in NOISE_PATTERNS:
        if re.match(pattern, line_lower, re.IGNORECASE):
            return True

    # Additional strict filtering for high-value pages
    if strict:
        for pattern in HIGH_VALUE_NOISE_PATTERNS:
            if pattern in line_lower:
                return True

    return False


def clean_html_for_diff(html: str) -> str:
    """
    Clean HTML content for diff comparison on high-value pages.

    Removes:
    - Cookie banners and consent dialogs
    - Script and style tags
    - Tracking parameters from URLs
    - Common boilerplate elements
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, and other non-content elements
    for tag in soup.find_all([
        "script", "style", "noscript", "iframe",
        "svg", "canvas", "video", "audio"
    ]):
        tag.decompose()

    # Remove common cookie/consent banner patterns
    cookie_selectors = [
        "[class*='cookie']",
        "[class*='consent']",
        "[class*='gdpr']",
        "[class*='privacy-banner']",
        "[id*='cookie']",
        "[id*='consent']",
        "[id*='gdpr']",
        "#CybotCookiebotDialog",
        ".cc-banner",
        ".cookie-notice",
    ]
    for selector in cookie_selectors:
        try:
            for el in soup.select(selector):
                el.decompose()
        except:
            pass  # Ignore selector errors

    # Remove hidden elements
    for el in soup.find_all(style=re.compile(r'display:\s*none', re.I)):
        el.decompose()

    # Remove tracking parameters from URLs
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "utm_" in href or "ref=" in href:
            # Strip tracking params
            href = re.sub(r'[?&](utm_[^&]+|ref=[^&]+)', '', href)
            a["href"] = href

    return str(soup)


def normalize_text(text: str, strict: bool = False) -> list[str]:
    """
    Normalize text into comparable lines.

    Args:
        text: The text to normalize
        strict: If True, apply stricter filtering for high-value pages
    """
    # Split into lines
    lines = text.split("\n")

    # Normalize whitespace and filter empty lines
    lines = [re.sub(r"\s+", " ", line.strip()) for line in lines]
    lines = [line for line in lines if line]

    # Apply noise filtering
    if strict:
        lines = [line for line in lines if not is_noise_line(line, strict=True)]

    return lines


def compute_high_value_diff(old_html: str, new_html: str) -> DiffResult:
    """
    Compute a diff optimized for high-value pages (team, portfolio, investments).

    Applies aggressive noise filtering to avoid false positives from:
    - Cookie banners
    - Timestamps
    - Social sharing buttons
    - Tracking parameters

    Args:
        old_html: Previous snapshot HTML
        new_html: Current snapshot HTML

    Returns:
        DiffResult with change analysis
    """
    # Clean both HTML documents
    old_clean = clean_html_for_diff(old_html)
    new_clean = clean_html_for_diff(new_html)

    # Extract text
    from .fetcher import extract_text_from_html
    old_text, _ = extract_text_from_html(old_clean)
    new_text, _ = extract_text_from_html(new_clean)

    # Normalize with strict filtering
    old_lines = normalize_text(old_text, strict=True)
    new_lines = normalize_text(new_text, strict=True)

    if not old_lines and not new_lines:
        return DiffResult(
            has_changes=False,
            is_meaningful=False,
            change_ratio=0.0,
            added_lines=[],
            removed_lines=[],
            summary="Both snapshots empty after cleaning",
        )

    # Use SequenceMatcher for similarity ratio
    matcher = SequenceMatcher(None, old_lines, new_lines)
    similarity = matcher.ratio()
    change_ratio = 1.0 - similarity

    # Get added and removed lines
    added_lines = []
    removed_lines = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added_lines.extend(new_lines[j1:j2])
        elif tag == "delete":
            removed_lines.extend(old_lines[i1:i2])
        elif tag == "replace":
            removed_lines.extend(old_lines[i1:i2])
            added_lines.extend(new_lines[j1:j2])

    # Even stricter filtering for final output
    meaningful_added = [line for line in added_lines if len(line) > 10 and not is_noise_line(line, strict=True)]
    meaningful_removed = [line for line in removed_lines if len(line) > 10 and not is_noise_line(line, strict=True)]

    # Determine if changes are meaningful (higher threshold for high-value pages)
    has_changes = len(meaningful_added) > 0 or len(meaningful_removed) > 0
    total_added_chars = sum(len(line) for line in meaningful_added)

    # Require more substantial changes for high-value pages
    is_meaningful = (
        has_changes
        and change_ratio >= 0.02  # At least 2% change
        and (
            total_added_chars >= 100  # At least 100 chars of new content
            or len(meaningful_added) >= 3  # Or at least 3 meaningful lines
        )
    )

    # Generate summary
    if not has_changes:
        summary = "No meaningful changes (noise filtered)"
    elif not is_meaningful:
        summary = f"Minor changes filtered ({len(added_lines)} raw, {len(meaningful_added)} meaningful)"
    else:
        parts = []
        if meaningful_added:
            parts.append(f"{len(meaningful_added)} sections added")
        if meaningful_removed:
            parts.append(f"{len(meaningful_removed)} sections removed")
        summary = ", ".join(parts) if parts else "Content modified"

    return DiffResult(
        has_changes=has_changes,
        is_meaningful=is_meaningful,
        change_ratio=change_ratio,
        added_lines=meaningful_added[:20],
        removed_lines=meaningful_removed[:20],
        summary=summary,
    )


def compute_diff(old_text: str, new_text: str) -> DiffResult:
    """
    Compute a meaningful diff between two text contents.

    Args:
        old_text: Previous snapshot text
        new_text: Current snapshot text

    Returns:
        DiffResult with change analysis
    """
    if not old_text and not new_text:
        return DiffResult(
            has_changes=False,
            is_meaningful=False,
            change_ratio=0.0,
            added_lines=[],
            removed_lines=[],
            summary="Both snapshots are empty",
        )

    if not old_text:
        return DiffResult(
            has_changes=True,
            is_meaningful=True,
            change_ratio=1.0,
            added_lines=normalize_text(new_text)[:20],
            removed_lines=[],
            summary="New content (first snapshot)",
        )

    if not new_text:
        return DiffResult(
            has_changes=True,
            is_meaningful=True,
            change_ratio=1.0,
            added_lines=[],
            removed_lines=normalize_text(old_text)[:20],
            summary="Content removed (page empty or error)",
        )

    old_lines = normalize_text(old_text)
    new_lines = normalize_text(new_text)

    # Use SequenceMatcher for similarity ratio
    matcher = SequenceMatcher(None, old_lines, new_lines)
    similarity = matcher.ratio()
    change_ratio = 1.0 - similarity

    # Get added and removed lines
    added_lines = []
    removed_lines = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added_lines.extend(new_lines[j1:j2])
        elif tag == "delete":
            removed_lines.extend(old_lines[i1:i2])
        elif tag == "replace":
            removed_lines.extend(old_lines[i1:i2])
            added_lines.extend(new_lines[j1:j2])

    # Filter out noise
    meaningful_added = [line for line in added_lines if not is_noise_line(line)]
    meaningful_removed = [line for line in removed_lines if not is_noise_line(line)]

    # Determine if changes are meaningful
    has_changes = len(added_lines) > 0 or len(removed_lines) > 0
    total_added_chars = sum(len(line) for line in meaningful_added)

    is_meaningful = (
        has_changes
        and change_ratio >= MIN_CHANGE_RATIO
        and (
            total_added_chars >= MIN_ADDED_CHARS
            or len(meaningful_added) >= MIN_MEANINGFUL_LINES
            or len(meaningful_removed) >= MIN_MEANINGFUL_LINES
        )
    )

    # Generate summary
    if not has_changes:
        summary = "No changes detected"
    elif not is_meaningful:
        summary = f"Minor changes ({len(added_lines)} lines, likely noise)"
    else:
        parts = []
        if meaningful_added:
            parts.append(f"{len(meaningful_added)} lines added")
        if meaningful_removed:
            parts.append(f"{len(meaningful_removed)} lines removed")
        summary = ", ".join(parts) if parts else "Content modified"

    return DiffResult(
        has_changes=has_changes,
        is_meaningful=is_meaningful,
        change_ratio=change_ratio,
        added_lines=meaningful_added[:20],  # Limit for storage
        removed_lines=meaningful_removed[:20],
        summary=summary,
    )


def _is_boilerplate(text: str) -> bool:
    """Check if text is likely boilerplate/noise."""
    boilerplate_markers = [
        "cookie", "privacy", "terms", "copyright", "all rights",
        "subscribe", "newsletter", "follow us", "share this",
        "read more", "learn more", "click here", "accept", "reject",
        "loading", "please wait", "javascript", "enable javascript",
    ]
    text_lower = text.lower()
    return any(marker in text_lower for marker in boilerplate_markers)


def _extract_meaningful_headline(lines: list[str]) -> str | None:
    """
    Extract a meaningful headline from added lines.

    Filters out noise and returns the first substantive line.
    """
    for line in lines:
        line = line.strip()
        # Skip short lines
        if len(line) < 30:
            continue
        # Skip boilerplate
        if _is_boilerplate(line):
            continue
        # Skip lines that are mostly punctuation/numbers
        alpha_ratio = sum(1 for c in line if c.isalpha()) / max(len(line), 1)
        if alpha_ratio < 0.5:
            continue
        return line
    return None


def generate_what_changed(diff: DiffResult, page_title: str | None = None) -> str:
    """
    Generate a human-readable "what changed" summary for a signal.

    Phase 7 enhancement: Extracts actual headlines/content instead of
    generic descriptions.

    Args:
        diff: The diff result
        page_title: Optional page title for context

    Returns:
        A concise description of what changed
    """
    if not diff.has_changes:
        return "No changes detected"

    if not diff.is_meaningful:
        return "Minor formatting changes"

    # Phase 7: Try to extract meaningful headline from added content
    if diff.added_lines:
        # Filter out noise and find meaningful lines
        meaningful_lines = [
            line for line in diff.added_lines
            if len(line) > 30 and not _is_boilerplate(line)
        ]

        if meaningful_lines:
            # Take the first meaningful line as the headline
            headline = _extract_meaningful_headline(meaningful_lines)
            if headline:
                # Truncate if too long
                if len(headline) > 500:
                    headline = headline[:497] + "..."
                # Add count if there are more lines
                if len(meaningful_lines) > 1:
                    return f"{headline} (+{len(meaningful_lines)-1} more updates)"
                return headline

    # Fallback: keyword-based classification
    parts = []

    # Add context from page title
    if page_title:
        parts.append(f"Changes detected on '{page_title}':")

    # Summarize additions
    if diff.added_lines:
        # Try to identify what kind of content was added
        added_text = " ".join(diff.added_lines[:5])

        if any(kw in added_text.lower() for kw in ["join", "hiring", "career", "position", "job"]):
            parts.append("New job posting or hiring information added")
        elif any(kw in added_text.lower() for kw in ["invest", "portfolio", "acquisition", "deal"]):
            parts.append("New investment or portfolio company mentioned")
        elif any(kw in added_text.lower() for kw in ["team", "partner", "director", "manager"]):
            parts.append("Team page updated with new members")
        elif any(kw in added_text.lower() for kw in ["fund", "raise", "close", "commit"]):
            parts.append("Fundraising information updated")
        elif any(kw in added_text.lower() for kw in ["news", "press", "announce"]):
            parts.append("New press release or announcement")
        else:
            # Generic summary with actual content preview
            preview = added_text[:200] + "..." if len(added_text) > 200 else added_text
            parts.append(f"New content: {preview}")

    # Note removals if significant
    if diff.removed_lines and len(diff.removed_lines) > 5:
        parts.append(f"Some content was removed ({len(diff.removed_lines)} sections)")

    return " ".join(parts) if parts else diff.summary


def _compute_item_fingerprint(title: str, date: str | None) -> str:
    """Compute a fingerprint for a news item."""
    text = f"{title.lower().strip()}|{date or ''}"
    return hashlib.md5(text.encode()).hexdigest()[:12]


_ITALIAN_MONTH_MAP: dict[str, str] = {
    "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
    "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
    "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12",
    # Abbreviated
    "gen": "01", "feb": "02", "mar": "03", "apr": "04",
    "mag": "05", "giu": "06", "lug": "07", "ago": "08",
    "set": "09", "ott": "10", "nov": "11", "dic": "12",
}

_ENGLISH_MONTH_MAP: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

_ALL_MONTH_MAP: dict[str, str] = {**_ITALIAN_MONTH_MAP, **_ENGLISH_MONTH_MAP}


def _normalize_date(date_str: str) -> str | None:
    """Try to normalize a date string to YYYY-MM-DD format.

    Handles Italian month names (full + abbreviated), location prefixes
    like 'Padova, 16 Gen. 2026', DD/MM/YYYY, and standard ISO formats.
    """
    if not date_str:
        return None

    s = date_str.strip()

    # Already ISO YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # ISO datetime — take date part
    if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        return s[:10]

    # Strip location prefix: "Padova, 16 Gen. 2026" → "16 Gen. 2026"
    s = re.sub(r"^[A-Za-zÀ-ú]+,\s*", "", s)

    # Strip dots from abbreviated months: "Gen." → "Gen"
    s = s.replace(".", "")

    # Pattern: "MonthName DD, YYYY" or "MonthName DD YYYY" (e.g. "Gennaio 29, 2026")
    m = re.match(r"^([A-Za-zÀ-ú]+)\s+(\d{1,2}),?\s+(\d{4})$", s)
    if m:
        month = _ALL_MONTH_MAP.get(m.group(1).lower())
        if month:
            return f"{m.group(3)}-{month}-{m.group(2).zfill(2)}"

    # Pattern: "DD MonthName YYYY" (e.g. "16 Gen 2026")
    m = re.match(r"^(\d{1,2})\s+([A-Za-zÀ-ú]+)\s+(\d{4})$", s)
    if m:
        month = _ALL_MONTH_MAP.get(m.group(2).lower())
        if month:
            return f"{m.group(3)}-{month}-{m.group(1).zfill(2)}"

    # DD/MM/YYYY or D/M/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    # DD-MM-YYYY
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    # Standard English month patterns: "15 January 2024"
    m = re.search(
        r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{4})",
        s, re.IGNORECASE
    )
    if m:
        month = _ALL_MONTH_MAP.get(m.group(2).lower()[:3])
        if month:
            return f"{m.group(3)}-{month}-{m.group(1).zfill(2)}"

    return date_str  # Return original if no pattern matched


def extract_news_items(html: str, base_url: str = "") -> list[NewsItem]:
    """
    Extract news/press items from HTML content.

    Phase 2 enhancement: First tries site-specific extraction using site_extractor.py,
    then falls back to generic heuristics.

    Looks for common patterns:
    - Article elements
    - List items with dates and titles
    - News card patterns

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving relative links

    Returns:
        List of NewsItem objects
    """
    # Try site-specific extraction first (Phase 2)
    try:
        site_extract = _get_site_extractor()
        extracted_items = site_extract(html, base_url)
        if extracted_items and len(extracted_items) >= 1:
            # Convert ExtractedNewsItem to NewsItem
            items: list[NewsItem] = []
            for item in extracted_items:
                items.append(NewsItem(
                    title=item["title"],
                    date=item["date"],
                    url=item["url"],
                    fingerprint=item["fingerprint"],
                ))
            return items
    except Exception as e:
        # Fall through to generic extraction
        pass

    # Fallback: Generic heuristic extraction
    soup = BeautifulSoup(html, "html.parser")
    items: list[NewsItem] = []
    seen_fingerprints: set[str] = set()

    # Remove nav, footer, header (usually not news content)
    for tag in soup.find_all(["nav", "footer", "header", "aside"]):
        tag.decompose()

    # Strategy 1: Look for article elements
    for article in soup.find_all("article"):
        title_el = article.find(["h1", "h2", "h3", "h4", "a"])
        if not title_el:
            continue

        title = title_el.get_text(separator=" ", strip=True)
        if len(title) < 10:  # Skip very short titles
            continue

        # Look for date
        date_el = article.find(["time", "span", "p"], class_=lambda c: c and any(
            x in str(c).lower() for x in ["date", "time", "published"]
        ))
        date = date_el.get_text(strip=True) if date_el else None
        date = _normalize_date(date) if date else None

        # Look for link
        link_el = article.find("a", href=True)
        url = link_el["href"] if link_el else None
        if url and not url.startswith("http"):
            url = base_url.rstrip("/") + "/" + url.lstrip("/")

        fingerprint = _compute_item_fingerprint(title, date)
        if fingerprint not in seen_fingerprints:
            seen_fingerprints.add(fingerprint)
            items.append(NewsItem(
                title=_normalize_signal_title(title),
                date=date,
                url=url,
                fingerprint=fingerprint,
            ))

    # Strategy 2: Look for list items with links and dates
    if len(items) < 3:  # Fallback if article strategy didn't find enough
        for li in soup.find_all("li"):
            link = li.find("a", href=True)
            if not link:
                continue

            title = link.get_text(separator=" ", strip=True)
            if len(title) < 10:
                continue

            # Look for date nearby
            text = li.get_text()
            date_match = re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", text)
            date = _normalize_date(date_match.group()) if date_match else None

            url = link.get("href", "")
            if url and not url.startswith("http"):
                url = base_url.rstrip("/") + "/" + url.lstrip("/")

            fingerprint = _compute_item_fingerprint(title, date)
            if fingerprint not in seen_fingerprints:
                seen_fingerprints.add(fingerprint)
                items.append(NewsItem(
                    title=_normalize_signal_title(title),
                    date=date,
                    url=url,
                    fingerprint=fingerprint,
                ))

    return items[:50]  # Limit to 50 items


def compare_news_items(
    old_items: list[NewsItem],
    new_items: list[NewsItem],
) -> NewsPageResult:
    """
    Compare news items between two snapshots.

    Args:
        old_items: Items from previous snapshot
        new_items: Items from current snapshot

    Returns:
        NewsPageResult with new and changed items
    """
    old_fingerprints = {item["fingerprint"]: item for item in old_items}
    new_fingerprints = {item["fingerprint"]: item for item in new_items}

    # Find new items (fingerprint not in old)
    new_found = [
        item for item in new_items
        if item["fingerprint"] not in old_fingerprints
    ]

    # Find items that might have changed (same title base, different date)
    # This is a simplified check - could be enhanced
    old_titles = {item["title"].lower(): item for item in old_items}
    changed = []
    for item in new_items:
        title_lower = item["title"].lower()
        if title_lower in old_titles and old_titles[title_lower]["fingerprint"] != item["fingerprint"]:
            changed.append(item)

    return NewsPageResult(
        items=new_items,
        new_items=new_found,
        changed_items=changed,
    )


# Keywords for classifying news signals by content type
# Order matters! More specific patterns should come first.
NEWS_CLASSIFICATION_RULES = [
    # (keywords, signal_type, is_noise)

    # IMPORTANT: Check for our own generated signal prefixes FIRST (before noise filters)
    # These are signals we generated from extraction, not raw page content
    (["new investment:", "new portfolio"], "deal_announced", False),
    (["new exit:"], "exit_announced", False),
    (["new team member"], "people_move", False),

    # Noise patterns to filter out - English
    (["cookie", "privacy", "gdpr", "terms of service", "terms and conditions"], None, True),
    # Noise patterns - Italian navigation/generic words (standalone only)
    (["successivo", "precedente", "pagina", "menu", "contatti", "chi siamo"], None, True),
    # Noise patterns - Italian section headers (not news)
    (["governance", "green harvest", "la nostra storia", "i nostri valori"], None, True),

    # Exit announcements - Italian (check BEFORE deals, "cede" is more specific)
    (["cede ", "ceduto", "cessione", "dismette", "disinveste", "vendita di", "vende ", "ha venduto"], "exit_announced", False),
    # Exit announcements - English
    (["exit", "exits", "sale of", "sold", "ipo", "divest", "divestment", "listing"], "exit_announced", False),
    # Deal announcements - Italian
    (["acquisisce", "acquisizione", "rileva", "rilevato", "investe in", "entra nel capitale", "prende il controllo"], "deal_announced", False),
    # Deal announcements - English
    (["acquisition", "acquire", "portfolio company", "deal", "transaction", "minority stake", "majority stake"], "deal_announced", False),
    # Fundraise announcements
    (["fund raise", "fundraise", "raising", "close", "closing", "commit", "committed"], "fundraise_announced", False),
    # People moves - Italian
    (["nomina", "nominato", "entra nel team", "nuovo partner", "nuovo direttore"], "people_move", False),
    # People moves - English
    (["appoint", "appointed", "join", "joins", "joined", "welcome", "welcomes"], "people_move", False),
    # Job postings / career signals - Italian
    (["lavora con noi", "posizione aperta", "cerchiamo", "selezione", "recruiting"], "job_posting", False),
    # Job postings / career signals - English
    (["hiring", "job opening", "career", "careers", "vacancy", "we're looking", "open position", "open role"], "job_posting", False),
]


def classify_news_signal(title: str) -> tuple[bool, str]:
    """
    Classify a news signal by its title content.

    Args:
        title: The news item title

    Returns:
        (should_keep, signal_type) - False if it's noise (cookie/privacy notices)
    """
    title_lower = title.lower().strip()

    # Filter very short titles (likely navigation/buttons)
    if len(title_lower) < 20:
        return False, "noise"

    # Filter single-word titles (likely section headers)
    if " " not in title_lower:
        return False, "noise"

    for keywords, signal_type, is_noise in NEWS_CLASSIFICATION_RULES:
        if any(kw in title_lower for kw in keywords):
            if is_noise:
                return False, "noise"
            return True, signal_type

    # Default: keep it but mark as generic "other" type
    return True, "other"


@dataclass
class NormalizedDiffResult:
    """Result of comparing two snapshots using the normalizer."""
    has_changes: bool
    is_meaningful: bool
    change_ratio: float
    added_lines: list[str]
    removed_lines: list[str]
    summary: str
    # Normalization metadata
    old_noise_removed: int
    new_noise_removed: int
    old_main_chars: int
    new_main_chars: int
    normalized_hash_old: str
    normalized_hash_new: str


def compute_normalized_diff(old_html: str, new_html: str) -> NormalizedDiffResult:
    """
    Compute a diff using the normalizer for aggressive noise removal.

    This is the Sprint 2 enhanced version of compute_high_value_diff that uses
    the dedicated normalizer module for more comprehensive noise removal.

    Args:
        old_html: Previous snapshot HTML
        new_html: Current snapshot HTML

    Returns:
        NormalizedDiffResult with change analysis and normalization metadata
    """
    normalizer = _get_normalizer()

    # Normalize both documents
    old_normalized = normalizer.normalize(old_html)
    new_normalized = normalizer.normalize(new_html)

    # Quick check: if hashes match, no changes
    if old_normalized.content_hash_normalized == new_normalized.content_hash_normalized:
        return NormalizedDiffResult(
            has_changes=False,
            is_meaningful=False,
            change_ratio=0.0,
            added_lines=[],
            removed_lines=[],
            summary="No changes (normalized content identical)",
            old_noise_removed=old_normalized.noise_removed_count,
            new_noise_removed=new_normalized.noise_removed_count,
            old_main_chars=old_normalized.main_content_chars,
            new_main_chars=new_normalized.main_content_chars,
            normalized_hash_old=old_normalized.content_hash_normalized,
            normalized_hash_new=new_normalized.content_hash_normalized,
        )

    # Split into lines for detailed diff
    old_lines = normalize_text(old_normalized.main_text, strict=True)
    new_lines = normalize_text(new_normalized.main_text, strict=True)

    if not old_lines and not new_lines:
        return NormalizedDiffResult(
            has_changes=False,
            is_meaningful=False,
            change_ratio=0.0,
            added_lines=[],
            removed_lines=[],
            summary="Both snapshots empty after normalization",
            old_noise_removed=old_normalized.noise_removed_count,
            new_noise_removed=new_normalized.noise_removed_count,
            old_main_chars=0,
            new_main_chars=0,
            normalized_hash_old=old_normalized.content_hash_normalized,
            normalized_hash_new=new_normalized.content_hash_normalized,
        )

    # Compute similarity
    matcher = SequenceMatcher(None, old_lines, new_lines)
    similarity = matcher.ratio()
    change_ratio = 1.0 - similarity

    # Extract changes
    added_lines = []
    removed_lines = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added_lines.extend(new_lines[j1:j2])
        elif tag == "delete":
            removed_lines.extend(old_lines[i1:i2])
        elif tag == "replace":
            removed_lines.extend(old_lines[i1:i2])
            added_lines.extend(new_lines[j1:j2])

    # Filter for meaningful changes
    meaningful_added = [line for line in added_lines if len(line) > 10 and not is_noise_line(line, strict=True)]
    meaningful_removed = [line for line in removed_lines if len(line) > 10 and not is_noise_line(line, strict=True)]

    has_changes = len(meaningful_added) > 0 or len(meaningful_removed) > 0
    total_added_chars = sum(len(line) for line in meaningful_added)

    # Higher threshold for meaningful changes when using normalization
    is_meaningful = (
        has_changes
        and change_ratio >= 0.02
        and (
            total_added_chars >= 100
            or len(meaningful_added) >= 3
        )
    )

    # Generate summary
    if not has_changes:
        summary = "No meaningful changes (noise filtered)"
    elif not is_meaningful:
        summary = f"Minor changes filtered ({len(added_lines)} raw, {len(meaningful_added)} meaningful)"
    else:
        parts = []
        if meaningful_added:
            parts.append(f"{len(meaningful_added)} sections added")
        if meaningful_removed:
            parts.append(f"{len(meaningful_removed)} sections removed")
        summary = ", ".join(parts) if parts else "Content modified"

    return NormalizedDiffResult(
        has_changes=has_changes,
        is_meaningful=is_meaningful,
        change_ratio=change_ratio,
        added_lines=meaningful_added[:20],
        removed_lines=meaningful_removed[:20],
        summary=summary,
        old_noise_removed=old_normalized.noise_removed_count,
        new_noise_removed=new_normalized.noise_removed_count,
        old_main_chars=old_normalized.main_content_chars,
        new_main_chars=new_normalized.main_content_chars,
        normalized_hash_old=old_normalized.content_hash_normalized,
        normalized_hash_new=new_normalized.content_hash_normalized,
    )


@dataclass
class TeamPageResult:
    """Result of comparing team pages."""
    has_new_members: bool
    new_members: list[str]  # Names of new team members
    total_current: int
    total_previous: int


def extract_team_members(html: str) -> list[str]:
    """
    Extract team member names from HTML content.

    Looks for common patterns in team pages:
    - Names in heading tags (h2, h3, h4)
    - Names in specific team card patterns
    - Names with titles like "Partner", "Director", "Managing"

    Args:
        html: Raw HTML content

    Returns:
        List of extracted names (deduplicated)
    """
    soup = BeautifulSoup(html, "html.parser")
    names: set[str] = set()

    # Remove nav, footer, header
    for tag in soup.find_all(["nav", "footer", "header", "aside", "script", "style"]):
        tag.decompose()

    # Common title patterns that indicate a person's role
    title_patterns = [
        r"partner",
        r"director",
        r"managing",
        r"principal",
        r"analyst",
        r"associate",
        r"vice president",
        r"vp\b",
        r"ceo",
        r"cfo",
        r"cio",
        r"founder",
    ]
    title_regex = re.compile(r"\b(" + "|".join(title_patterns) + r")\b", re.IGNORECASE)

    # Strategy 1: Look for names in team card structures
    # Common patterns: div with class containing "team", "member", "person"
    team_selectors = [
        "[class*='team']",
        "[class*='member']",
        "[class*='person']",
        "[class*='staff']",
        "[class*='employee']",
    ]

    for selector in team_selectors:
        try:
            for card in soup.select(selector):
                # Look for name in heading
                name_el = card.find(["h2", "h3", "h4", "h5", "strong"])
                if name_el:
                    name = name_el.get_text(strip=True)
                    # Validate: looks like a name (2-4 words, capitalized)
                    if _looks_like_name(name):
                        names.add(name)
        except:
            pass

    # Strategy 2: Look for headings followed by role titles
    for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
        name = heading.get_text(strip=True)
        if _looks_like_name(name):
            # Check if nearby text contains a role title
            next_sibling = heading.find_next_sibling()
            if next_sibling:
                sibling_text = next_sibling.get_text().lower()
                if title_regex.search(sibling_text):
                    names.add(name)

    # Strategy 3: Look for name patterns in links
    for link in soup.find_all("a"):
        text = link.get_text(strip=True)
        if _looks_like_name(text):
            # Check parent for team-related classes
            parent = link.parent
            if parent:
                parent_classes = " ".join(parent.get("class", []))
                if any(kw in parent_classes.lower() for kw in ["team", "member", "person", "staff"]):
                    names.add(text)

    return sorted(names)


def _looks_like_name(text: str) -> bool:
    """
    Check if text looks like a person's name.

    Criteria:
    - 2-5 words
    - Each word starts with capital letter
    - No numbers or special characters (except periods, hyphens)
    - Not too long (max 50 chars)
    """
    if not text or len(text) > 50 or len(text) < 3:
        return False

    words = text.split()
    if len(words) < 2 or len(words) > 5:
        return False

    # Check each word is capitalized and contains only letters
    for word in words:
        word_clean = word.rstrip(".,")
        if not word_clean:
            continue
        if not word_clean[0].isupper():
            return False
        if not re.match(r"^[A-Za-z\'-]+\.?$", word_clean):
            return False

    # Filter out common non-name patterns
    text_lower = text.lower()
    noise_words = ["cookie", "privacy", "contact", "about", "news", "home", "team", "our"]
    if any(noise in text_lower for noise in noise_words):
        return False

    return True


def compare_team_members(old_html: str, new_html: str) -> TeamPageResult:
    """
    Compare team members between two HTML snapshots.

    Args:
        old_html: Previous snapshot HTML
        new_html: Current snapshot HTML

    Returns:
        TeamPageResult with new members detected
    """
    old_members = set(extract_team_members(old_html))
    new_members = set(extract_team_members(new_html))

    # Find truly new members
    added = new_members - old_members

    return TeamPageResult(
        has_new_members=len(added) > 0,
        new_members=sorted(added),
        total_current=len(new_members),
        total_previous=len(old_members),
    )
