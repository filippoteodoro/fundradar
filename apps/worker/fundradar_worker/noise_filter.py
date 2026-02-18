"""
Noise filtering for HTML content extraction.

Removes non-relevant content like cookie banners, navigation,
footer boilerplate, social sharing buttons, and other noise
before extracting meaningful data.
"""

import re
from bs4 import BeautifulSoup, Tag


# CSS selectors for elements to remove
NOISE_SELECTORS = [
    # Navigation and structure
    "nav",
    "footer",
    "header",
    "aside",

    # Cookie and consent
    ".cookie-banner",
    ".cookie-notice",
    ".consent-modal",
    ".consent-banner",
    ".privacy-banner",
    "#cookie-banner",
    "#cookie-notice",
    "#CybotCookiebotDialog",
    "#onetrust-consent-sdk",
    ".cc-banner",
    ".cc-window",
    "[class*='cookie']",
    "[class*='consent']",
    "[class*='gdpr']",
    "[id*='cookie']",
    "[id*='consent']",
    "[id*='gdpr']",

    # Newsletter and subscription
    ".newsletter",
    ".newsletter-signup",
    ".subscribe-box",
    ".subscription",
    "[class*='newsletter']",
    "[class*='subscribe']",

    # Social and sharing (specific classes only)
    ".social-share",
    ".share-buttons",
    ".social-links",
    ".social-media",
    ".share-bar",
    ".social-icons",
    "[class~='social-share']",
    "[class~='share-buttons']",

    # Overlays and popups (be specific to avoid matching e.g. 'hasnt-overlay-header')
    ".modal",
    ".popup",
    ".overlay",
    ".modal-overlay",
    ".popup-overlay",
    ".content-overlay",
    "[class~='modal']",  # Use ~= for exact class match
    "[class~='popup']",
    "[class~='overlay']",

    # Ads and tracking (be specific to avoid false positives)
    ".ads",
    ".ad-container",
    ".ad-banner",
    ".advertisement",
    ".ad-slot",
    "[class~='ad']",
    "[class~='ads']",
    "[class~='advertisement']",
    "[class~='sponsor']",

    # Chat widgets (specific classes only)
    ".chat-widget",
    ".live-chat",
    ".chat-box",
    ".chat-container",
    "[class~='chat']",
    "#chat-widget",

    # Hidden elements
    "[aria-hidden='true']",
    "[hidden]",
    ".hidden",
    ".hide",
    ".invisible",

    # Script-related
    "script",
    "noscript",
    "style",
    "iframe",
    "svg",
    "canvas",
]

# Text patterns that indicate noise content
NOISE_TEXT_PATTERNS = [
    # Cookie/consent related
    r"\bcookie(?:s)?\b",
    r"\bconsent\b",
    r"\bgdpr\b",
    r"\bprivacy\s+policy\b",
    r"\bterms\s+of\s+service\b",
    r"\bterms\s+and\s+conditions\b",

    # Navigation boilerplate
    r"^menu$",
    r"^nav(?:igation)?$",
    r"^header$",
    r"^footer$",

    # Subscription/newsletter
    r"\bsubscribe\b",
    r"\bnewsletter\b",
    r"\bsign\s+up\b",
    r"\bcontact\s+us\b",

    # Social media
    r"\bshare\s+on\b",
    r"\bfollow\s+us\b",
    r"\blinkedin\.com/shareArticle\b",
    r"\btwitter\.com/intent\b",
    r"\bfacebook\.com/sharer\b",

    # UI elements
    r"^loading\.{0,3}$",
    r"^please\s+wait\b",
    r"^accept(?:\s+all)?$",
    r"^reject(?:\s+all)?$",
    r"^close$",
    r"^dismiss$",
    r"^ok$",
    r"^cancel$",
    r"^submit$",

    # Generic noise
    r"^©\s*\d{4}",
    r"\ball\s+rights\s+reserved\b",
    r"\bcopyright\b",

    # Tracking
    r"\butm_",
]

# Compile patterns for efficiency
_COMPILED_NOISE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in NOISE_TEXT_PATTERNS]


def remove_noise_elements(soup: BeautifulSoup) -> tuple[BeautifulSoup, int]:
    """
    Remove noise elements from a BeautifulSoup object.

    Args:
        soup: The BeautifulSoup object to clean

    Returns:
        Tuple of (cleaned soup, count of elements removed)
    """
    removed_count = 0

    for selector in NOISE_SELECTORS:
        try:
            for element in soup.select(selector):
                element.decompose()
                removed_count += 1
        except Exception:
            # Some selectors might fail on certain HTML structures
            pass

    # Remove elements with display:none style
    for element in soup.find_all(style=re.compile(r'display:\s*none', re.IGNORECASE)):
        element.decompose()
        removed_count += 1

    # Remove elements with visibility:hidden style
    for element in soup.find_all(style=re.compile(r'visibility:\s*hidden', re.IGNORECASE)):
        element.decompose()
        removed_count += 1

    return soup, removed_count


def is_noise_text(text: str) -> bool:
    """
    Check if text matches noise patterns.

    Args:
        text: The text to check

    Returns:
        True if text appears to be noise
    """
    if not text or not text.strip():
        return True

    text = text.strip()

    # Very short text (less than 3 chars) is likely noise
    if len(text) < 3:
        return True

    # Check against compiled patterns
    text_lower = text.lower()
    for pattern in _COMPILED_NOISE_PATTERNS:
        if pattern.search(text_lower):
            return True

    # Pure numbers are often counters/IDs
    if text.isdigit():
        return True

    return False


def is_boilerplate_element(element: Tag) -> bool:
    """
    Check if an element is likely boilerplate/noise based on attributes.

    Args:
        element: BeautifulSoup Tag element

    Returns:
        True if element appears to be boilerplate
    """
    if not isinstance(element, Tag):
        return False

    # Check class names
    classes = element.get("class", [])
    if isinstance(classes, str):
        classes = [classes]

    class_str = " ".join(classes).lower()
    boilerplate_classes = [
        "cookie", "consent", "gdpr", "privacy",
        "footer", "header", "nav", "navigation",
        "social", "share", "newsletter", "subscribe",
        "popup", "modal", "overlay", "ad", "ads",
    ]

    for bp in boilerplate_classes:
        if bp in class_str:
            return True

    # Check ID
    element_id = element.get("id", "").lower()
    if element_id:
        for bp in boilerplate_classes:
            if bp in element_id:
                return True

    # Check role attribute
    role = element.get("role", "").lower()
    if role in ("banner", "navigation", "contentinfo", "complementary"):
        return True

    return False


def clean_text(text: str) -> str:
    """
    Clean text by removing excessive whitespace and noise.

    Args:
        text: Text to clean

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    return text


def extract_main_content(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Try to extract the main content area from the page.

    Looks for common main content containers like <main>, <article>,
    or divs with content-related classes.

    Args:
        soup: The BeautifulSoup object

    Returns:
        BeautifulSoup of main content (or original if not found)
    """
    # Priority list of main content selectors
    main_selectors = [
        "main",
        "[role='main']",
        "article",
        ".main-content",
        ".content",
        "#main-content",
        "#content",
        ".page-content",
        ".entry-content",
        ".post-content",
    ]

    for selector in main_selectors:
        try:
            main = soup.select_one(selector)
            if main and len(main.get_text(strip=True)) > 100:
                return BeautifulSoup(str(main), "html.parser")
        except Exception:
            pass

    # Return original if no main content found
    return soup


def remove_noise(html: str) -> tuple[str, int]:
    """
    Remove noise from HTML content.

    This is the main entry point for noise removal.

    Args:
        html: Raw HTML content

    Returns:
        Tuple of (cleaned HTML, count of elements removed)
    """
    soup = BeautifulSoup(html, "html.parser")
    soup, removed_count = remove_noise_elements(soup)
    return str(soup), removed_count


def get_clean_soup(html: str) -> tuple[BeautifulSoup, int]:
    """
    Get a cleaned BeautifulSoup object with noise removed.

    Args:
        html: Raw HTML content

    Returns:
        Tuple of (cleaned BeautifulSoup, count of elements removed)
    """
    soup = BeautifulSoup(html, "html.parser")
    return remove_noise_elements(soup)


class NoiseFilter:
    """
    Configurable noise filter for HTML content.

    Allows customizing the noise patterns and selectors for
    site-specific filtering.
    """

    def __init__(
        self,
        extra_selectors: list[str] | None = None,
        extra_patterns: list[str] | None = None,
        keep_selectors: list[str] | None = None,
    ):
        """
        Initialize the noise filter.

        Args:
            extra_selectors: Additional CSS selectors to remove
            extra_patterns: Additional text patterns (regex) to filter
            keep_selectors: CSS selectors to preserve (override noise removal)
        """
        self.selectors = list(NOISE_SELECTORS)
        if extra_selectors:
            self.selectors.extend(extra_selectors)

        self.patterns = list(_COMPILED_NOISE_PATTERNS)
        if extra_patterns:
            self.patterns.extend([
                re.compile(p, re.IGNORECASE) for p in extra_patterns
            ])

        self.keep_selectors = keep_selectors or []

    def filter(self, html: str) -> tuple[BeautifulSoup, int]:
        """
        Filter noise from HTML content.

        Args:
            html: Raw HTML content

        Returns:
            Tuple of (cleaned BeautifulSoup, count removed)
        """
        soup = BeautifulSoup(html, "html.parser")
        removed_count = 0

        # Find elements to keep
        elements_to_keep = set()
        for selector in self.keep_selectors:
            try:
                for el in soup.select(selector):
                    elements_to_keep.add(id(el))
                    # Also keep all descendants
                    for desc in el.descendants:
                        if hasattr(desc, '__hash__'):
                            elements_to_keep.add(id(desc))
            except Exception:
                pass

        # Remove noise elements
        for selector in self.selectors:
            try:
                for element in soup.select(selector):
                    if id(element) not in elements_to_keep:
                        element.decompose()
                        removed_count += 1
            except Exception:
                pass

        # Remove hidden elements
        for element in soup.find_all(style=re.compile(r'display:\s*none', re.IGNORECASE)):
            if id(element) not in elements_to_keep:
                element.decompose()
                removed_count += 1

        return soup, removed_count

    def is_noise(self, text: str) -> bool:
        """
        Check if text is noise.

        Args:
            text: Text to check

        Returns:
            True if text appears to be noise
        """
        if not text or not text.strip():
            return True

        text = text.strip()

        if len(text) < 3:
            return True

        text_lower = text.lower()
        for pattern in self.patterns:
            if pattern.search(text_lower):
                return True

        if text.isdigit():
            return True

        return False
