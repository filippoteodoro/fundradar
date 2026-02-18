"""
Enhanced news extractor.

Extracts news/press items from fund websites with improved URL extraction
and deal type detection.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..noise_filter import remove_noise_elements, is_noise_text
from ..site_config_schema import SiteConfig, site_config_from_dict

logger = logging.getLogger(__name__)


@dataclass
class ExtractedNewsItem:
    """A news item extracted from a website."""
    title: str
    url: str | None = None
    date: str | None = None  # YYYY-MM-DD format
    date_raw: str | None = None
    description: str | None = None
    company_mentioned: str | None = None
    deal_type: str | None = None  # acquisition, exit, fundraise, investment
    deal_value: str | None = None  # e.g., "€50M", "$100M"
    confidence: float = 0.5
    fingerprint: str = ""
    sources: list[str] = field(default_factory=list)


class NewsExtractor:
    """
    Extracts news items from HTML content.

    Enhanced version of the site_extractor with:
    - Better article URL extraction
    - Deal type detection
    - Deal value extraction
    - Company name extraction

    Usage:
        extractor = NewsExtractor()
        items = extractor.extract(html, url)
    """

    # Deal type keywords
    DEAL_KEYWORDS = {
        "acquisition": ["acquire", "acquisition", "acquires", "acquista", "acquisizione", "bought", "purchase"],
        "exit": ["exit", "exits", "ipo", "quotazione", "cede", "ceduta", "divest", "divestment", "sale", "sold"],
        "fundraise": ["fund", "raise", "raising", "close", "closing", "commit", "committed", "capital", "raccolta"],
        "investment": ["invest", "investe", "investimento", "partecipazione", "backs", "backed"],
    }

    # Value patterns (€50M, $100 million, etc.)
    VALUE_PATTERNS = [
        r"€\s*(\d+(?:\.\d+)?)\s*(M|million|mln|B|billion|bln)?",
        r"\$\s*(\d+(?:\.\d+)?)\s*(M|million|mln|B|billion|bln)?",
        r"(\d+(?:\.\d+)?)\s*(M|million|mln|B|billion|bln)\s*(?:€|\$|euro|dollar)",
    ]

    def __init__(self, config_path: Path | None = None):
        """
        Initialize the extractor.

        Args:
            config_path: Optional path to site_extractors.json
        """
        self._site_configs: dict[str, dict] = {}
        self._month_names: dict[str, str] = {}

        if config_path and config_path.exists():
            self._load_site_configs(config_path)

    def _load_site_configs(self, config_path: Path):
        """Load site-specific configurations."""
        try:
            with open(config_path) as f:
                data = json.load(f)
                self._site_configs = data.get("sites", {})
                self._month_names = {}
                for lang_months in data.get("date_parsing", {}).get("month_names", {}).values():
                    self._month_names.update(lang_months)
        except Exception as e:
            logger.warning(f"Failed to load site configs: {e}")
            self._month_names = {}

    def _get_site_config(self, url: str) -> dict | None:
        """Get site configuration for a URL."""
        domain = urlparse(url).netloc.lower()
        return self._site_configs.get(domain, {}).get("news")

    def extract(
        self,
        html: str,
        base_url: str,
        config: dict | None = None,
    ) -> list[ExtractedNewsItem]:
        """
        Extract news items from HTML.

        Args:
            html: Raw HTML content
            base_url: Base URL for resolving relative links
            config: Optional news extraction config

        Returns:
            List of ExtractedNewsItem objects
        """
        # Get config if not provided
        if config is None:
            config = self._get_site_config(base_url) or {}

        soup = BeautifulSoup(html, "html.parser")

        # Remove noise elements
        soup, removed = remove_noise_elements(soup)
        logger.debug(f"Removed {removed} noise elements")

        items = []
        seen_fingerprints: set[str] = set()

        # Get selectors
        item_sel = config.get("item_selector", "article, .news-item, .post, [class*='news']")
        title_sel = config.get("title_selector", "h2 a, h3 a, .title a, a")
        date_sel = config.get("date_selector", "time, .date, [datetime]")
        link_sel = config.get("link_selector", "a[href]")
        desc_sel = config.get("description_selector", ".excerpt, .summary, p")

        # Find items
        found_items = []
        for sel in item_sel.split(", "):
            try:
                found_items.extend(soup.select(sel))
            except Exception:
                continue

        # Dedupe items (remove nested)
        unique_items = self._dedupe_elements(found_items)

        for element in unique_items[:50]:  # Limit to 50
            item = self._extract_item(
                element,
                base_url,
                title_sel,
                date_sel,
                link_sel,
                desc_sel,
                config,
            )

            if item and item.fingerprint not in seen_fingerprints:
                seen_fingerprints.add(item.fingerprint)
                items.append(item)

        # If we found very few items, try bare-text fallback extraction
        # This handles sites like progressio that have no CSS structure
        if len(items) < 3:
            logger.debug(f"Only found {len(items)} items with selectors, trying bare-text fallback")
            fallback_items = self._extract_from_bare_text(soup, base_url)
            for item in fallback_items:
                if item.fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(item.fingerprint)
                    items.append(item)
            logger.debug(f"Bare-text fallback found {len(fallback_items)} additional items")

        logger.info(f"Extracted {len(items)} news items")
        return items

    def _dedupe_elements(self, elements: list) -> list:
        """Remove nested elements (keep outermost)."""
        unique = []
        for el in elements:
            is_nested = False
            for existing in unique:
                if el in existing.descendants or existing in el.descendants:
                    is_nested = True
                    break
            if not is_nested:
                unique.append(el)
        return unique

    def _extract_item(
        self,
        element,
        base_url: str,
        title_sel: str,
        date_sel: str,
        link_sel: str,
        desc_sel: str,
        config: dict,
    ) -> ExtractedNewsItem | None:
        """Extract a single news item from an element."""
        # Extract title
        title = None
        title_url = None

        for sel in title_sel.split(", "):
            try:
                title_el = element.select_one(sel)
                if title_el:
                    title = title_el.get_text(separator=" ", strip=True)
                    if title_el.name == "a" and title_el.get("href"):
                        title_url = title_el["href"]
                    break
            except Exception:
                continue

        if not title or len(title) < 10:
            return None

        # Skip noise
        if is_noise_text(title):
            return None

        # Extract URL
        url = title_url
        if not url:
            for sel in link_sel.split(", "):
                try:
                    link_el = element.select_one(sel)
                    if link_el and link_el.get("href"):
                        href = link_el["href"]
                        # Skip anchors and javascript
                        if not href.startswith(("#", "javascript:")):
                            url = href
                            break
                except Exception:
                    continue

        # Resolve relative URL
        if url and not url.startswith(("http://", "https://")):
            url = urljoin(base_url, url)

        # Extract date
        date = None
        date_raw = None

        # Try configured selectors first
        for sel in date_sel.split(", "):
            try:
                date_el = element.select_one(sel)
                if date_el:
                    # Try datetime attribute first
                    date_raw = date_el.get("datetime") or date_el.get_text(strip=True)
                    if date_raw:
                        date = self._parse_date(date_raw, config.get("date_format"))
                        if date:
                            break
            except Exception:
                continue

        # Fallback: look for date patterns in element text
        if not date:
            element_text = element.get_text()
            # Look for common date patterns
            date_patterns = [
                r"\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4}",  # 15 - 01 - 2024 (with spaces)
                r"\d{1,2}/\d{1,2}/\d{4}",  # 15/01/2024
                r"\d{1,2}-\d{1,2}-\d{4}",  # 15-01-2024
                r"\d{4}-\d{1,2}-\d{1,2}",  # 2024-01-15
                r"\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4}",
                r"\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}",
            ]
            for pattern in date_patterns:
                match = re.search(pattern, element_text, re.IGNORECASE)
                if match:
                    date_raw = match.group()
                    date = self._parse_date(date_raw)
                    if date:
                        break

        # Extract description
        description = None
        for sel in desc_sel.split(", "):
            try:
                desc_el = element.select_one(sel)
                if desc_el:
                    desc_text = desc_el.get_text(separator=" ", strip=True)
                    if desc_text and len(desc_text) > 20 and not is_noise_text(desc_text):
                        description = desc_text[:500]
                        break
            except Exception:
                continue

        # Extract deal info
        combined_text = f"{title} {description or ''}"
        company = self._extract_company_name(combined_text)
        deal_type = self._classify_deal_type(combined_text)
        deal_value = self._extract_deal_value(combined_text)

        # Calculate confidence
        confidence = 0.5
        if url and url != base_url:
            confidence += 0.2  # Has article URL
        if date:
            confidence += 0.1  # Has parsed date
        if description:
            confidence += 0.1  # Has description
        if deal_type:
            confidence += 0.05  # Detected deal type

        # Compute fingerprint
        fingerprint = self._compute_fingerprint(title, date, url)

        return ExtractedNewsItem(
            title=title[:200],
            url=url,
            date=date,
            date_raw=date_raw,
            description=description,
            company_mentioned=company,
            deal_type=deal_type,
            deal_value=deal_value,
            confidence=min(confidence, 1.0),
            fingerprint=fingerprint,
            sources=["html"],
        )

    def _parse_date(self, date_str: str, date_format: str | None = None) -> str | None:
        """Parse date string to YYYY-MM-DD format."""
        if not date_str:
            return None

        date_str = date_str.strip()
        original_date_str = date_str

        # Handle relative dates first (Italian and English)
        relative_date = self._parse_relative_date(date_str)
        if relative_date:
            return relative_date

        # Replace month names with numbers (Italian and English)
        month_names = {
            # Italian full
            "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
            "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
            "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12",
            # English full
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12",
            # English short
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "jun": "06", "jul": "07", "aug": "08", "sep": "09",
            "oct": "10", "nov": "11", "dec": "12",
            # Italian short
            "gen": "01", "feb": "02", "mar": "03", "apr": "04",
            "mag": "05", "giu": "06", "lug": "07", "ago": "08",
            "set": "09", "ott": "10", "nov": "11", "dic": "12",
        }

        date_lower = date_str.lower()
        for month_name, month_num in month_names.items():
            if month_name in date_lower:
                date_str = re.sub(
                    r'\b' + re.escape(month_name) + r'\b',
                    month_num,
                    date_str,
                    flags=re.IGNORECASE
                )
                break

        # Also try stored month names
        for month_name, month_num in self._month_names.items():
            if month_name in date_lower:
                date_str = re.sub(
                    r'\b' + re.escape(month_name) + r'\b',
                    month_num,
                    date_str,
                    flags=re.IGNORECASE
                )
                break

        # Common patterns - order matters (more specific first)
        patterns = [
            # ISO format: 2024-01-15
            (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"),
            # European with 4-digit year: 15/01/2024 or 15.01.2024
            (r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"),
            # European with dash and spaces: 15 - 01 - 2024 (progressio style)
            (r"(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{4})", lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"),
            # European with dash (no spaces): 15-01-2024
            (r"(\d{1,2})-(\d{1,2})-(\d{4})", lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"),
            # Date with replaced month: "15 01 2024" or "15, 01, 2024"
            (r"(\d{1,2})[,\s]+(\d{2})[,\s]+(\d{4})", lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1).zfill(2)}"),
            # European with 2-digit year: 15/01/24
            (r"(\d{1,2})/(\d{1,2})/(\d{2})(?!\d)", lambda m: f"20{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"),
            # Just day and month with year elsewhere: "15 01" when we know the year
            (r"^(\d{1,2})\s+(\d{2})$", lambda m: f"{datetime.now().year}-{m.group(2)}-{m.group(1).zfill(2)}"),
        ]

        for pattern, formatter in patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    result = formatter(match)
                    # Validate the date
                    parsed = datetime.strptime(result, "%Y-%m-%d")
                    # Sanity check: not in the future, not too old
                    if parsed.year >= 2010 and parsed <= datetime.now():
                        return result
                except ValueError:
                    continue

        # Try to extract year from original string and combine with found date parts
        year_match = re.search(r'\b(20\d{2})\b', original_date_str)
        if year_match:
            year = year_match.group(1)
            # Try to find day/month pattern
            day_month_match = re.search(r'(\d{1,2})\s+(\d{2})', date_str)
            if day_month_match:
                try:
                    result = f"{year}-{day_month_match.group(2)}-{day_month_match.group(1).zfill(2)}"
                    datetime.strptime(result, "%Y-%m-%d")
                    return result
                except ValueError:
                    pass

        return None

    def _parse_relative_date(self, date_str: str) -> str | None:
        """Parse relative date expressions to YYYY-MM-DD format."""
        date_lower = date_str.lower().strip()
        today = datetime.now()

        # Italian relative dates
        italian_patterns = [
            (r"oggi", 0),
            (r"ieri", 1),
            (r"l'altro ieri|l'altroieri|altroieri", 2),
            (r"(\d+)\s*(?:giorn[oi]|gg)\s*fa", None),  # X giorni fa
            (r"(\d+)\s*settiman[ae]\s*fa", None),  # X settimane fa
            (r"(\d+)\s*mes[ei]\s*fa", None),  # X mesi fa
            (r"una\s*settimana\s*fa", 7),
            (r"un\s*mese\s*fa", 30),
        ]

        # English relative dates
        english_patterns = [
            (r"today", 0),
            (r"yesterday", 1),
            (r"(\d+)\s*days?\s*ago", None),
            (r"(\d+)\s*weeks?\s*ago", None),
            (r"(\d+)\s*months?\s*ago", None),
            (r"a\s*week\s*ago|one\s*week\s*ago", 7),
            (r"a\s*month\s*ago|one\s*month\s*ago", 30),
        ]

        all_patterns = italian_patterns + english_patterns

        for pattern, days_ago in all_patterns:
            match = re.search(pattern, date_lower)
            if match:
                if days_ago is not None:
                    result_date = today - timedelta(days=days_ago)
                else:
                    # Extract the number
                    num = int(match.group(1))
                    if "settiman" in pattern or "week" in pattern:
                        result_date = today - timedelta(weeks=num)
                    elif "mes" in pattern or "month" in pattern:
                        result_date = today - timedelta(days=num * 30)
                    else:
                        result_date = today - timedelta(days=num)

                return result_date.strftime("%Y-%m-%d")

        return None

    def _classify_deal_type(self, text: str) -> str | None:
        """Classify the deal type from text."""
        text_lower = text.lower()

        for deal_type, keywords in self.DEAL_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return deal_type

        return None

    def _extract_company_name(self, text: str) -> str | None:
        """Extract company name from text."""
        # Pattern: "in" followed by capitalized words (with optional legal suffix)
        patterns = [
            r"\bin\s+([A-Z][A-Za-z\s&]+(?:S\.?p\.?A\.?|S\.?r\.?l\.?|Ltd\.?|Inc\.?)?)",
            r"^([A-Z][A-Za-z\s&]+(?:S\.?p\.?A\.?|S\.?r\.?l\.?))\s+(?:acquired|sold|exits)",
            r"(?:investe|invests|backs|acquires)\s+(?:in\s+)?([A-Z][A-Za-z\s&]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                company = match.group(1).strip()
                if len(company) > 2 and len(company) < 100:
                    return company

        return None

    def _extract_deal_value(self, text: str) -> str | None:
        """Extract deal value from text."""
        for pattern in self.VALUE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Reconstruct the value string
                return match.group(0).strip()

        return None

    def _compute_fingerprint(self, title: str, date: str | None, url: str | None) -> str:
        """Compute fingerprint for deduplication."""
        text = f"{title.lower().strip()}|{date or ''}|{url or ''}"
        return hashlib.md5(text.encode()).hexdigest()[:12]

    def _extract_from_bare_text(self, soup: BeautifulSoup, base_url: str) -> list[ExtractedNewsItem]:
        """
        Fallback extraction for sites with non-standard HTML (no CSS classes).

        Looks for patterns like:
        - Date text (e.g., "07 - 01 - 2026" or "07/01/2026") followed by heading with link
        - Heading with link, followed by date text

        This handles sites like progressio.it where news items have minimal structure.
        """
        items = []
        seen_fingerprints: set[str] = set()

        # Date patterns to look for in bare text
        bare_date_patterns = [
            r"(\d{1,2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{4})",  # 07-01-2026 or 07/01/2026
            r"(\d{1,2})\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})",
        ]

        # Look for headings that might be news titles
        for heading in soup.find_all(['h2', 'h3', 'h4']):
            # Get the link in or around the heading
            link_el = heading.find('a')
            if not link_el:
                # Check if heading is inside a link
                parent_link = heading.find_parent('a')
                if parent_link:
                    link_el = parent_link

            if not link_el:
                continue

            # Get title and URL
            title = heading.get_text(separator=" ", strip=True)
            if not title or len(title) < 10:
                continue

            # Skip noise
            if is_noise_text(title):
                continue

            href = link_el.get('href')
            if not href or href.startswith(('#', 'javascript:')):
                continue

            url = href
            if not url.startswith(('http://', 'https://')):
                url = urljoin(base_url, url)

            # Look for date near the heading
            date = None
            date_raw = None

            # Check siblings and parent for date patterns
            search_elements = []

            # Previous siblings
            prev_el = heading.find_previous_sibling()
            if prev_el:
                search_elements.append(prev_el)

            # Next siblings
            next_el = heading.find_next_sibling()
            if next_el:
                search_elements.append(next_el)

            # Parent's text
            parent = heading.parent
            if parent:
                search_elements.append(parent)

            for el in search_elements:
                el_text = el.get_text() if el else ""
                for pattern in bare_date_patterns:
                    match = re.search(pattern, el_text, re.IGNORECASE)
                    if match:
                        date_raw = match.group(0)
                        date = self._parse_date(date_raw)
                        if date:
                            break
                if date:
                    break

            # Calculate confidence
            confidence = 0.5
            if url and url != base_url:
                confidence += 0.2
            if date:
                confidence += 0.15
            # Lower confidence for bare-text extraction
            confidence *= 0.9

            fingerprint = self._compute_fingerprint(title, date, url)
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)

            item = ExtractedNewsItem(
                title=title[:200],
                url=url,
                date=date,
                date_raw=date_raw,
                description=None,
                company_mentioned=self._extract_company_name(title),
                deal_type=self._classify_deal_type(title),
                deal_value=self._extract_deal_value(title),
                confidence=min(confidence, 1.0),
                fingerprint=fingerprint,
                sources=["bare_text"],
            )
            items.append(item)

        return items

    def save_results(
        self,
        items: list[ExtractedNewsItem],
        fund_slug: str,
        output_dir: Path,
    ) -> Path:
        """
        Save extraction results to JSON file.

        Args:
            items: Extracted news items
            fund_slug: Fund identifier
            output_dir: Output directory

        Returns:
            Path to saved file
        """
        # Create fund directory
        fund_dir = output_dir / fund_slug
        fund_dir.mkdir(parents=True, exist_ok=True)

        # Save news data
        path = fund_dir / "news.json"

        data = {
            "fund_slug": fund_slug,
            "data_type": "news",
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "count": len(items),
            "items": [asdict(i) for i in items],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(items)} news items to {path}")
        return path


def extract_news_items(
    html: str,
    base_url: str,
    config: dict | None = None,
) -> list[ExtractedNewsItem]:
    """
    Convenience function to extract news items.

    Args:
        html: Raw HTML content
        base_url: Base URL
        config: Optional extraction config

    Returns:
        List of ExtractedNewsItem objects
    """
    extractor = NewsExtractor()
    return extractor.extract(html, base_url, config)
