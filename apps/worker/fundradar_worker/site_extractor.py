"""
Site-specific content extraction for Fundradar.

Loads extraction rules from site_extractors.json and provides
functions to extract structured data (news items, portfolio companies)
from HTML using site-specific CSS selectors.

This module handles content extraction using site-specific CSS selectors
and extraction rules.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ExtractedNewsItem(TypedDict):
    """A news item extracted using site-specific rules."""
    title: str
    url: str | None        # Actual article URL (not list page)
    date: str | None       # Parsed date YYYY-MM-DD
    date_raw: str | None   # Original date string
    description: str | None
    company_name: str | None  # If extractable from title
    deal_type: str | None     # acquisition, investment, exit
    fingerprint: str          # Hash for change detection


@dataclass
class SiteExtractorConfig:
    """Configuration for extracting content from a specific site."""
    domain: str
    page_type: str  # news, portfolio, team
    list_url: str | None
    item_selector: str
    title_selector: str
    date_selector: str | None
    date_format: str | None
    link_selector: str | None
    description_selector: str | None
    company_name_attr: str | None = None


class SiteExtractorLoader:
    """
    Loads and caches site extraction configurations from JSON.

    The JSON file contains site-specific CSS selectors for extracting
    news items, portfolio companies, etc.
    """

    def __init__(self, config_path: Path | None = None):
        """
        Initialize the loader.

        Args:
            config_path: Path to site_extractors.json. If None, uses default location.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "data" / "derived" / "site_extractors.json"

        self.config_path = config_path
        self._config: dict | None = None
        self._load()

    def _load(self):
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            logger.warning(f"Site extractors config not found: {self.config_path}")
            self._config = {"sites": {}, "defaults": {}}
            return

        try:
            with open(self.config_path) as f:
                self._config = json.load(f)
            logger.info(f"Loaded site extractors config with {len(self._config.get('sites', {}))} sites")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load site extractors config: {e}")
            self._config = {"sites": {}, "defaults": {}}

    def get_config(self, url: str, page_type: str) -> SiteExtractorConfig | None:
        """
        Get extraction config for a URL and page type.

        Args:
            url: Full URL or domain
            page_type: Type of page (news, portfolio, team)

        Returns:
            SiteExtractorConfig if found, None otherwise
        """
        # Extract domain
        if url.startswith(("http://", "https://")):
            domain = urlparse(url).netloc.lower()
        else:
            domain = url.lower()

        # Try site-specific config
        site_config = self._config.get("sites", {}).get(domain, {}).get(page_type)

        if site_config:
            return SiteExtractorConfig(
                domain=domain,
                page_type=page_type,
                list_url=site_config.get("list_url"),
                item_selector=site_config.get("item_selector", ""),
                title_selector=site_config.get("title_selector", ""),
                date_selector=site_config.get("date_selector"),
                date_format=site_config.get("date_format"),
                link_selector=site_config.get("link_selector"),
                description_selector=site_config.get("description_selector"),
                company_name_attr=site_config.get("company_name_attr"),
            )

        # Fall back to defaults
        defaults = self._config.get("defaults", {}).get(page_type)
        if defaults:
            return SiteExtractorConfig(
                domain=domain,
                page_type=page_type,
                list_url=None,
                item_selector=defaults.get("item_selector", ""),
                title_selector=defaults.get("title_selector", ""),
                date_selector=defaults.get("date_selector"),
                date_format=None,  # Use all formats for defaults
                link_selector=defaults.get("link_selector"),
                description_selector=defaults.get("description_selector"),
            )

        return None

    def get_date_formats(self) -> list[str]:
        """Get list of supported date formats from config."""
        defaults = self._config.get("defaults", {}).get("news", {})
        return defaults.get("date_formats", [
            "DD MMMM YYYY",
            "DD/MM/YYYY",
            "DD-MM-YYYY",
            "YYYY-MM-DD",
            "MMMM DD, YYYY",
        ])

    def get_month_names(self) -> dict[str, str]:
        """Get month name mappings from config."""
        date_parsing = self._config.get("date_parsing", {})
        month_names = date_parsing.get("month_names", {})

        # Combine Italian and English month names
        combined = {}
        for lang_months in month_names.values():
            combined.update(lang_months)

        return combined

    def reload(self):
        """Reload configuration from disk."""
        self._load()


# Global loader instance
_loader: SiteExtractorLoader | None = None


def get_loader() -> SiteExtractorLoader:
    """Get the global site extractor loader."""
    global _loader
    if _loader is None:
        _loader = SiteExtractorLoader()
    return _loader


def parse_date(date_str: str, date_format: str | None = None) -> str | None:
    """
    Parse a date string into YYYY-MM-DD format.

    Handles multiple date formats and Italian/English month names.

    Args:
        date_str: Raw date string
        date_format: Optional specific format to try first

    Returns:
        Normalized date string YYYY-MM-DD, or None if unparseable
    """
    if not date_str:
        return None

    date_str = date_str.strip()
    loader = get_loader()
    month_names = loader.get_month_names()

    # Replace month names with numbers
    date_lower = date_str.lower()
    for month_name, month_num in month_names.items():
        if month_name in date_lower:
            date_str = re.sub(
                re.escape(month_name),
                month_num,
                date_str,
                flags=re.IGNORECASE
            )
            break

    # Common date patterns
    patterns = [
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"),
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"),
        (r"(\d{1,2})-(\d{1,2})-(\d{4})", lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"),
        (r"(\d{1,2})\s+(\d{2})\s+(\d{4})", lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1).zfill(2)}"),  # After month replacement
        (r"(\d{2})\s+(\d{1,2}),?\s*(\d{4})", lambda m: f"{m.group(3)}-{m.group(1)}-{m.group(2).zfill(2)}"),  # Month DD, YYYY after replacement
    ]

    for pattern, formatter in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                result = formatter(match)
                # Validate the date
                datetime.strptime(result, "%Y-%m-%d")
                return result
            except ValueError:
                continue

    return None


def compute_fingerprint(title: str, date: str | None, url: str | None) -> str:
    """Compute a fingerprint for a news item."""
    import hashlib
    text = f"{title.lower().strip()}|{date or ''}|{url or ''}"
    return hashlib.md5(text.encode()).hexdigest()[:12]


def classify_deal_type(title: str) -> str | None:
    """
    Classify the deal type from a news title.

    Returns: acquisition, investment, exit, fundraise, or None
    """
    title_lower = title.lower()

    if any(kw in title_lower for kw in ["acquire", "acquisition", "acquires", "acquista", "acquisizione"]):
        return "acquisition"
    elif any(kw in title_lower for kw in ["exit", "exits", "ipo", "quotazione", "cede", "ceduta"]):
        return "exit"
    elif any(kw in title_lower for kw in ["fund", "raise", "close", "closing", "raccolta", "fondo"]):
        return "fundraise"
    elif any(kw in title_lower for kw in ["invest", "investe", "investimento", "partecipazione"]):
        return "investment"

    return None


def extract_company_name(title: str) -> str | None:
    """
    Try to extract a company name from a news title.

    Looks for patterns like:
    - "Wise SGR acquires majority stake in ABC Company"
    - "Investment in XYZ SpA"
    """
    # Pattern: "in" followed by capitalized words
    match = re.search(r"\bin\s+([A-Z][A-Za-z\s&]+(?:S\.?p\.?A\.?|S\.?r\.?l\.?|Ltd\.?|Inc\.?)?)", title)
    if match:
        return match.group(1).strip()

    # Pattern: company at start followed by action verb
    match = re.search(r"^([A-Z][A-Za-z\s&]+(?:S\.?p\.?A\.?|S\.?r\.?l\.?))\s+(?:acquired|sold|exits)", title, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None


def extract_news_items_with_config(
    html: str,
    base_url: str,
    config: SiteExtractorConfig | None = None,
) -> list[ExtractedNewsItem]:
    """
    Extract news items from HTML using site-specific configuration.

    If no config is provided, uses default selectors.

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving relative links
        config: Optional site-specific extraction config

    Returns:
        List of ExtractedNewsItem objects
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[ExtractedNewsItem] = []
    seen_fingerprints: set[str] = set()

    # Remove nav, footer, header
    for tag in soup.find_all(["nav", "footer", "header", "aside"]):
        tag.decompose()

    # Get selectors
    if config:
        item_selectors = config.item_selector.split(", ")
        title_selectors = config.title_selector.split(", ") if config.title_selector else ["h2 a", "h3 a", "a"]
        date_selectors = config.date_selector.split(", ") if config.date_selector else ["time", ".date"]
        link_selectors = config.link_selector.split(", ") if config.link_selector else ["a[href]"]
        desc_selectors = config.description_selector.split(", ") if config.description_selector else [".excerpt", "p"]
    else:
        # Use generous defaults
        item_selectors = ["article", ".news-item", ".post", "[class*='news']", "li"]
        title_selectors = ["h2 a", "h3 a", ".entry-title a", "a.title", "a"]
        date_selectors = ["time", ".date", "[class*='date']", "[datetime]"]
        link_selectors = ["a[href]:not([href^='#'])"]
        desc_selectors = [".excerpt", ".summary", "p"]

    # Find items using each selector
    found_items = []
    for selector in item_selectors:
        try:
            found_items.extend(soup.select(selector))
        except Exception:
            pass

    # Deduplicate items by checking if one contains another
    unique_items = []
    for item in found_items:
        is_duplicate = False
        for existing in unique_items:
            if item in existing.descendants or existing in item.descendants:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_items.append(item)

    for item in unique_items[:50]:  # Limit to 50 items
        # Extract title
        title = None
        title_url = None
        for selector in title_selectors:
            try:
                title_el = item.select_one(selector)
                if title_el:
                    title = title_el.get_text(strip=True)
                    if title_el.name == "a" and title_el.get("href"):
                        title_url = title_el["href"]
                    break
            except Exception:
                pass

        if not title or len(title) < 10:
            continue

        # Extract URL (prefer title link, then link selector)
        url = title_url
        if not url:
            for selector in link_selectors:
                try:
                    link_el = item.select_one(selector)
                    if link_el and link_el.get("href"):
                        url = link_el["href"]
                        break
                except Exception:
                    pass

        # Resolve relative URL
        if url and not url.startswith(("http://", "https://")):
            url = urljoin(base_url, url)

        # Extract date
        date = None
        date_raw = None
        for selector in date_selectors:
            try:
                date_el = item.select_one(selector)
                if date_el:
                    # Try datetime attribute first
                    date_raw = date_el.get("datetime") or date_el.get_text(strip=True)
                    if date_raw:
                        date = parse_date(date_raw, config.date_format if config else None)
                        break
            except Exception:
                pass

        # Extract description
        description = None
        for selector in desc_selectors:
            try:
                desc_el = item.select_one(selector)
                if desc_el:
                    description = desc_el.get_text(strip=True)[:500]
                    break
            except Exception:
                pass

        # Extract additional info
        company_name = extract_company_name(title)
        deal_type = classify_deal_type(title)

        # Compute fingerprint
        fingerprint = compute_fingerprint(title, date, url)

        if fingerprint not in seen_fingerprints:
            seen_fingerprints.add(fingerprint)
            items.append(ExtractedNewsItem(
                title=title[:200],
                url=url,
                date=date,
                date_raw=date_raw,
                description=description,
                company_name=company_name,
                deal_type=deal_type,
                fingerprint=fingerprint,
            ))

    return items


def extract_news_items(html: str, base_url: str) -> list[ExtractedNewsItem]:
    """
    Extract news items from HTML, using site-specific config if available.

    This is the main entry point that automatically loads config.

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving relative links

    Returns:
        List of ExtractedNewsItem objects
    """
    loader = get_loader()
    config = loader.get_config(base_url, "news")
    return extract_news_items_with_config(html, base_url, config)
