"""
Content normalization for noise-resistant change detection.

Provides aggressive HTML cleaning to remove dynamic elements that would
cause false positive diffs (cookie banners, timestamps, social widgets, etc.).
"""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup, Comment


@dataclass
class NormalizedContent:
    """Result of content normalization."""
    main_text: str
    content_hash_normalized: str
    noise_removed_count: int
    main_content_chars: int
    extraction_method: str  # 'main_tag', 'article', 'heuristic', 'full_body'


class ContentNormalizer:
    """
    Normalizes HTML content for change detection.
    Removes noise (banners, popups, nav/footer) and extracts main content.
    """

    # CSS selectors for common noise elements
    NOISE_SELECTORS = [
        # Cookie/consent patterns
        "[class*='cookie']", "[class*='consent']", "[class*='gdpr']",
        "[id*='cookie']", "[id*='consent']", "[id*='gdpr']",
        "[class*='banner']", "[class*='modal']", "[class*='popup']",
        "[class*='overlay']", "[class*='subscribe']", "[class*='newsletter']",
        "[class*='announcement']", "[class*='notification']",
        # Legal/compliance
        ".privacy-notice", ".terms-notice", "[class*='legal']",
        "[class*='disclaimer']", "[class*='policy']",
        # Social/sharing widgets
        "[class*='social']", "[class*='share']", "[class*='follow']",
        "[class*='twitter']", "[class*='facebook']", "[class*='linkedin']",
        "[class*='instagram']", "[class*='youtube']",
        # Ads and tracking
        "[class*='ad-']", "[class*='ads']", "[class*='advertisement']",
        "[class*='sponsor']", "[class*='promo']",
        "[id*='ad-']", "[id*='ads']",
        # Chat widgets
        "[class*='chat']", "[class*='intercom']", "[class*='zendesk']",
        "[class*='drift']", "[class*='hubspot']",
        # Navigation noise
        "[class*='breadcrumb']", "[class*='pagination']",
        # Form elements (usually not content)
        "[class*='search-form']", "[class*='login-form']",
        # Lazy load placeholders
        "[class*='skeleton']", "[class*='placeholder']", "[class*='loading']",
        # Common specific selectors
        "#CybotCookiebotDialog", ".cc-banner", ".cookie-notice",
        ".privacy-banner", "#onetrust-consent-sdk", ".optanon-alert-box-wrapper",
    ]

    # Tags to always remove (not content)
    REMOVE_TAGS = [
        "script", "style", "noscript", "iframe", "svg", "canvas",
        "video", "audio", "template", "object", "embed",
    ]

    # Structural elements likely to be boilerplate
    BOILERPLATE_TAGS = [
        "nav", "footer", "header", "aside",
    ]

    # Patterns indicating timestamp/dynamic content
    TIMESTAMP_PATTERNS = [
        r"(?i)last updated:?\s*\d",
        r"(?i)modified:?\s*\d",
        r"(?i)published:?\s*\d",
        r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\s*\d{1,2}:\d{2}",  # Date with time
        r"(?i)(mon|tue|wed|thu|fri|sat|sun)\w*,?\s+\d",
        r"(?i)(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}",
        r"©\s*\d{4}",  # Copyright years
        r"©\s*\d{4}\s*[-–]\s*\d{4}",  # Copyright year ranges
        r"\d+\s*(views?|clicks?|likes?|shares?|comments?|reads?)",  # Counters
    ]

    # URL tracking parameters to strip
    TRACKING_PARAMS = [
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
        "_ga", "_gl", "hsCtaTracking",
    ]

    def normalize(self, html: str) -> NormalizedContent:
        """
        Normalize HTML content by removing noise and extracting main content.

        Args:
            html: Raw HTML string

        Returns:
            NormalizedContent with cleaned text and metadata
        """
        if not html or not html.strip():
            return NormalizedContent(
                main_text="",
                content_hash_normalized=self._compute_hash(""),
                noise_removed_count=0,
                main_content_chars=0,
                extraction_method="empty",
            )

        soup = BeautifulSoup(html, "html.parser")
        noise_count = 0

        # Remove HTML comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
            noise_count += 1

        # Remove always-remove tags
        for tag_name in self.REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()
                noise_count += 1

        # Remove noise elements by selector
        for selector in self.NOISE_SELECTORS:
            try:
                for el in soup.select(selector):
                    el.decompose()
                    noise_count += 1
            except Exception:
                pass  # Ignore selector errors

        # Remove hidden elements
        for el in soup.find_all(style=re.compile(r'display:\s*none', re.I)):
            el.decompose()
            noise_count += 1

        for el in soup.find_all(attrs={"hidden": True}):
            el.decompose()
            noise_count += 1

        for el in soup.find_all(attrs={"aria-hidden": "true"}):
            # Keep some aria-hidden elements that might contain real content
            if el.name not in ["span", "div"] or len(el.get_text(strip=True)) < 20:
                el.decompose()
                noise_count += 1

        # Normalize URLs (strip tracking params)
        self._normalize_urls(soup)

        # Remove boilerplate structural elements
        for tag_name in self.BOILERPLATE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()
                noise_count += 1

        # Extract main content
        main_text, extraction_method = self._extract_main_content(soup)

        # Clean the extracted text
        main_text = self._clean_text(main_text)

        # Remove timestamp noise from text
        main_text = self._remove_timestamp_noise(main_text)

        return NormalizedContent(
            main_text=main_text,
            content_hash_normalized=self._compute_hash(main_text),
            noise_removed_count=noise_count,
            main_content_chars=len(main_text),
            extraction_method=extraction_method,
        )

    def _normalize_urls(self, soup: BeautifulSoup):
        """Strip tracking parameters from all URLs in the document."""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            try:
                parsed = urlparse(href)
                if parsed.query:
                    params = parse_qs(parsed.query, keep_blank_values=True)
                    # Remove tracking params
                    filtered = {
                        k: v for k, v in params.items()
                        if k.lower() not in self.TRACKING_PARAMS
                    }
                    new_query = urlencode(filtered, doseq=True)
                    a["href"] = urlunparse(parsed._replace(query=new_query))
            except Exception:
                pass  # Keep original if parsing fails

    def _extract_main_content(self, soup: BeautifulSoup) -> tuple[str, str]:
        """
        Extract the main content from the cleaned HTML.

        Tries multiple strategies:
        1. <main> tag
        2. <article> tags
        3. Heuristic: largest content block
        4. Full body fallback

        Returns:
            (text_content, extraction_method)
        """
        # Strategy 1: Main tag
        main = soup.find("main")
        if main:
            text = main.get_text(separator="\n")
            if len(text.strip()) > 100:
                return text, "main_tag"

        # Strategy 2: Article tags (combine all)
        articles = soup.find_all("article")
        if articles:
            combined = "\n\n".join(a.get_text(separator="\n") for a in articles)
            if len(combined.strip()) > 100:
                return combined, "article"

        # Strategy 3: Heuristic - find largest text block
        body = soup.find("body") or soup
        candidates = []

        for tag in body.find_all(["div", "section"]):
            # Skip if has many nested divs (likely layout container)
            nested_divs = len(tag.find_all("div", recursive=False))
            if nested_divs > 5:
                continue

            text = tag.get_text(separator="\n")
            text_len = len(text.strip())

            # Prefer content-looking blocks
            if text_len > 200:
                # Score based on text density and length
                tag_count = len(tag.find_all())
                density = text_len / (tag_count + 1)
                score = text_len * (density / 100)
                candidates.append((score, text, tag))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_text = candidates[0][1]
            if len(best_text.strip()) > 100:
                return best_text, "heuristic"

        # Strategy 4: Full body fallback
        body = soup.find("body")
        if body:
            return body.get_text(separator="\n"), "full_body"

        return soup.get_text(separator="\n"), "full_document"

    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text."""
        # Normalize whitespace within lines
        lines = text.split("\n")
        lines = [re.sub(r"[ \t]+", " ", line.strip()) for line in lines]

        # Remove empty lines but preserve paragraph breaks
        cleaned_lines = []
        prev_empty = False
        for line in lines:
            if not line:
                if not prev_empty:
                    cleaned_lines.append("")
                prev_empty = True
            else:
                cleaned_lines.append(line)
                prev_empty = False

        text = "\n".join(cleaned_lines).strip()

        # Collapse multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text

    def _remove_timestamp_noise(self, text: str) -> str:
        """Remove common timestamp patterns that cause false positives."""
        for pattern in self.TIMESTAMP_PATTERNS:
            text = re.sub(pattern, "", text)

        # Clean up any double spaces created
        text = re.sub(r"  +", " ", text)

        return text

    def _compute_hash(self, text: str) -> str:
        """Compute a hash of the normalized text."""
        # Normalize for hash: lowercase, remove all whitespace
        normalized = re.sub(r"\s+", "", text.lower())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def normalize_for_diff(html: str) -> NormalizedContent:
    """
    Convenience function to normalize HTML for diff comparison.

    Args:
        html: Raw HTML string

    Returns:
        NormalizedContent with cleaned text and metadata
    """
    normalizer = ContentNormalizer()
    return normalizer.normalize(html)
