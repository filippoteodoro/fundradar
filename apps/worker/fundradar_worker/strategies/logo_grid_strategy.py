"""
Extraction strategy for logo/image grid layouts.

Many fund websites display portfolio companies as a grid of logos
with minimal text. This strategy extracts company names from image
alt text, nearby text, and URL patterns.
"""

import logging
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag

from ..noise_filter import is_noise_text

logger = logging.getLogger(__name__)


# Common patterns for logo grid containers
GRID_CONTAINER_PATTERNS = [
    "[class*='logo-grid']",
    "[class*='portfolio-grid']",
    "[class*='company-grid']",
    "[class*='partner-grid']",
    "[class*='client-grid']",
    "[class*='logos']",
    ".portfolio-logos",
    ".company-logos",
    ".grid",
]

# Common logo wrapper patterns
LOGO_WRAPPER_PATTERNS = [
    "[class*='logo']",
    "[class*='company']",
    "[class*='portfolio']",
    "[class*='partner']",
    ".grid-item",
    "li",
    "figure",
]


def extract_from_logo_grid(
    html: str,
    base_url: str,
    selectors: dict | None = None,
) -> list[dict]:
    """
    Extract companies from logo/image grids.

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving links
        selectors: Optional selector configuration

    Returns:
        List of company dictionaries
    """
    return extract_companies_from_logos(html, base_url, selectors)


def extract_companies_from_logos(
    html: str,
    base_url: str,
    selectors: dict | None = None,
) -> list[dict]:
    """
    Extract company information from logo grids.

    Attempts multiple strategies:
    1. Use provided selectors
    2. Find logo grid containers
    3. Extract from individual images with meaningful alt text

    Args:
        html: Raw HTML content
        base_url: Base URL
        selectors: Optional selector configuration

    Returns:
        List of company dictionaries
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_names = set()

    # Strategy 1: Use provided selectors
    if selectors:
        container_sel = selectors.get("container")
        item_sel = selectors.get("item")

        if container_sel and item_sel:
            container = soup.select_one(container_sel)
            if container:
                items = container.select(item_sel)
                for item in items:
                    company = _extract_from_logo_wrapper(item, base_url)
                    if company and company["name"] not in seen_names:
                        seen_names.add(company["name"])
                        results.append(company)

    # Strategy 2: Find grid containers
    if not results:
        for pattern in GRID_CONTAINER_PATTERNS:
            try:
                containers = soup.select(pattern)
                for container in containers:
                    # Find logo wrappers within container
                    for wrapper_pattern in LOGO_WRAPPER_PATTERNS:
                        items = container.select(wrapper_pattern)
                        for item in items:
                            company = _extract_from_logo_wrapper(item, base_url)
                            if company and company["name"] not in seen_names:
                                seen_names.add(company["name"])
                                results.append(company)

                    if results:
                        break

                if results:
                    break
            except Exception:
                continue

    # Strategy 3: Extract from all images with good alt text
    if not results:
        results = _extract_from_all_images(soup, base_url, seen_names)

    logger.info(f"Extracted {len(results)} companies from logo grid")
    return results


def _extract_from_logo_wrapper(
    wrapper: Tag,
    base_url: str,
) -> dict | None:
    """
    Extract company info from a logo wrapper element.

    Args:
        wrapper: Wrapper element containing logo
        base_url: Base URL for resolving links

    Returns:
        Company dictionary or None
    """
    company = {
        "name": None,
        "website": None,
        "logo_url": None,
        "sector": None,
        "description": None,
        "status": None,
        "source": "logo_grid",
    }

    # Find image
    img = wrapper.find("img")
    if img:
        # Get name from alt text
        alt = img.get("alt", "")
        if alt and _is_valid_company_name(alt):
            company["name"] = _clean_company_name(alt)

        # Get logo URL
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if src:
            company["logo_url"] = urljoin(base_url, src)

            # Try to get name from filename if no alt
            if not company["name"]:
                name_from_src = _extract_name_from_url(src)
                if name_from_src:
                    company["name"] = name_from_src

    # Check for link
    link = wrapper.find("a", href=True)
    if link:
        href = link["href"]

        # Get website if external link
        if href.startswith("http") and base_url not in href:
            company["website"] = href

            # Try to get name from URL if still missing
            if not company["name"]:
                name_from_href = _extract_name_from_url(href)
                if name_from_href:
                    company["name"] = name_from_href

        # Get name from link text if missing
        if not company["name"]:
            link_text = link.get_text(strip=True)
            if link_text and _is_valid_company_name(link_text):
                company["name"] = _clean_company_name(link_text)

    # Check for text nearby
    if not company["name"]:
        # Look for heading or span with text
        for tag in wrapper.find_all(["h1", "h2", "h3", "h4", "h5", "span", "p"]):
            text = tag.get_text(strip=True)
            if text and _is_valid_company_name(text):
                company["name"] = _clean_company_name(text)
                break

    # Check for title attribute
    if not company["name"]:
        title = wrapper.get("title")
        if title and _is_valid_company_name(title):
            company["name"] = _clean_company_name(title)

    # Only return if we found a name
    if company["name"]:
        return company

    return None


def _extract_from_all_images(
    soup: BeautifulSoup,
    base_url: str,
    seen_names: set,
) -> list[dict]:
    """
    Fallback: Extract from all images with meaningful alt text.

    Args:
        soup: BeautifulSoup object
        base_url: Base URL
        seen_names: Set of already seen names

    Returns:
        List of company dictionaries
    """
    results = []

    # Find images that look like logos
    for img in soup.find_all("img"):
        # Check alt text
        alt = img.get("alt", "")
        if not alt or not _is_valid_company_name(alt):
            continue

        # Check if in a likely portfolio/company section
        parent = img.parent
        parent_context = ""
        for _ in range(5):  # Check up to 5 levels up
            if parent:
                parent_context += " ".join(parent.get("class", []))
                parent = parent.parent

        if not any(kw in parent_context.lower() for kw in
                   ["portfolio", "company", "logo", "partner", "invest", "client"]):
            continue

        name = _clean_company_name(alt)
        if name in seen_names:
            continue

        seen_names.add(name)

        src = img.get("src") or img.get("data-src")
        logo_url = urljoin(base_url, src) if src else None

        results.append({
            "name": name,
            "logo_url": logo_url,
            "website": None,
            "sector": None,
            "description": None,
            "status": None,
            "source": "logo_grid",
        })

    return results


def _is_valid_company_name(text: str) -> bool:
    """
    Check if text could be a valid company name.

    Args:
        text: Text to validate

    Returns:
        True if text looks like a company name
    """
    if not text or len(text) < 2 or len(text) > 100:
        return False

    text = text.strip()

    # Reject noise patterns
    if is_noise_text(text):
        return False

    # Reject common non-company patterns
    noise_patterns = [
        r"^logo$",
        r"^image$",
        r"^company$",
        r"^portfolio$",
        r"^placeholder",
        r"^default",
        r"^loading",
        r"^\d+$",
        r"^img\d*$",
        r"^screen\s*shot",
        r"^untitled",
    ]

    text_lower = text.lower()
    for pattern in noise_patterns:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return False

    return True


def _clean_company_name(name: str) -> str:
    """
    Clean and normalize a company name.

    Args:
        name: Raw company name

    Returns:
        Cleaned name
    """
    if not name:
        return name

    name = name.strip()

    # Remove common suffixes/prefixes
    name = re.sub(r'\s*logo\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^logo\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*-\s*portfolio\s*$', '', name, flags=re.IGNORECASE)

    # Clean up whitespace
    name = re.sub(r'\s+', ' ', name)
    name = name.strip()

    return name


def _extract_name_from_url(url: str) -> str | None:
    """
    Try to extract a company name from a URL or filename.

    Args:
        url: URL or path

    Returns:
        Extracted name or None
    """
    if not url:
        return None

    # Parse URL
    parsed = urlparse(url)

    # Try hostname first (for company websites)
    if parsed.netloc and not any(generic in parsed.netloc for generic in
                                  ["cdn", "static", "image", "asset", "upload", "wp-content"]):
        # Extract domain without TLD
        domain = parsed.netloc.replace("www.", "")
        domain_parts = domain.split(".")
        if domain_parts:
            name = domain_parts[0]
            if len(name) > 2 and _is_valid_company_name(name):
                return name.replace("-", " ").replace("_", " ").title()

    # Try filename
    path = parsed.path
    if path:
        # Get filename without extension
        filename = path.split("/")[-1]
        name, _ = filename.rsplit(".", 1) if "." in filename else (filename, "")

        # Clean up common patterns
        name = re.sub(r'[-_]logo[-_]?', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[-_]', ' ', name)
        name = name.strip()

        if len(name) > 2 and _is_valid_company_name(name):
            return name.title()

    return None
