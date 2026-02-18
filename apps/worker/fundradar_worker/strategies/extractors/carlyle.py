"""Site-specific extractors for carlyle.com.

Note: This site returns 403 Forbidden for plain HTTP requests.
Requires headless browser (Playwright) for all fetches.

Portfolio page uses status filter via URL param:
- status=111 → Current investments
- status=116 → Exited investments
The extractor fetches both filtered pages via Playwright and tags
companies accordingly.
"""
import logging
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs

DOMAIN = "www.carlyle.com"


# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}
PORTFOLIO_BASE = "https://www.carlyle.com/portfolio"
STATUS_CURRENT = "111"
STATUS_EXITED = "116"

logger = logging.getLogger(__name__)


def _fetch_page_headless(url: str) -> str:
    """Fetch a page using Playwright (headless browser).

    Carlyle returns 403 for plain HTTP requests, so we need a real browser.
    Falls back to empty string if Playwright is unavailable.
    """
    try:
        from fundradar_worker.playwright_fetcher import fetch_with_playwright_sync
    except ImportError:
        logger.warning("Playwright fetcher not available for secondary Carlyle fetch")
        return ""

    try:
        result = fetch_with_playwright_sync(url)
        if result.html and result.status_code == 200:
            return result.html
        logger.info("Carlyle secondary fetch returned status %s", result.status_code)
        return ""
    except Exception as e:
        logger.warning("Carlyle secondary headless fetch failed: %s", e)
        return ""


def _extract_from_html(html: str, base_url: str, status: str,
                       seen_names: set) -> list[dict]:
    """Extract portfolio companies from a single page of Carlyle HTML.

    Structure: article.node--type-investment contains:
    - h3 > a[href] (external company website) > span (company name)
    - .field--name-field-industry .field__item (sector)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    for article in soup.select("article.node--type-investment"):
        h3 = article.select_one("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get company website from the h3 link (external link to company)
        website = None
        link = h3.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "carlyle" not in href.lower():
                website = href

        # Get sector from the field--name-field-industry
        sector = None
        industry_field = article.select_one(".field--name-field-industry .field__item")
        if industry_field:
            sector = industry_field.get_text(strip=True)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def _status_from_url(url: str) -> str | None:
    """Return the status filter value from a Carlyle portfolio URL, or None."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    values = params.get("status", [])
    return values[0] if values else None


def _build_filtered_url(status: str) -> str:
    """Build a Carlyle portfolio URL with the given status filter."""
    return f"{PORTFOLIO_BASE}?status={status}"


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Carlyle portfolio page.

    The provided HTML comes from a headless browser (reliable). We always
    extract from it first. Then we attempt a secondary urllib fetch for the
    other status filter — this is best-effort since Carlyle may 403 plain
    HTTP requests.
    """
    companies = []
    seen_names = set()

    # Determine which filter the provided HTML corresponds to
    url_status = _status_from_url(base_url)

    if url_status == STATUS_CURRENT:
        primary_status = "current"
        other_status_code = STATUS_EXITED
        other_status_label = "exited"
    elif url_status == STATUS_EXITED:
        primary_status = "exited"
        other_status_code = STATUS_CURRENT
        other_status_label = "current"
    else:
        # No filter param — treat provided HTML as current (best guess)
        primary_status = "current"
        other_status_code = STATUS_EXITED
        other_status_label = "exited"

    # Always extract from the headless-fetched HTML first
    companies.extend(
        _extract_from_html(html, base_url, primary_status, seen_names))

    # Fetch the other filtered page via Playwright (headless browser).
    # Carlyle 403s plain HTTP requests, so we need a real browser here too.
    other_url = _build_filtered_url(other_status_code)
    other_html = _fetch_page_headless(other_url)
    if other_html:
        other_companies = _extract_from_html(
            other_html, base_url, other_status_label, seen_names)
        if other_companies:
            companies.extend(other_companies)
            logger.info("Carlyle: fetched %d %s companies via headless browser",
                        len(other_companies), other_status_label)
        else:
            logger.warning("Carlyle: headless fetch for %s returned HTML but "
                           "no companies extracted", other_status_label)
    else:
        logger.warning("Carlyle: could not fetch %s investments page; "
                       "returning %d %s companies only",
                       other_status_label, len(companies), primary_status)

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Carlyle team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for heading in soup.find_all(["h2", "h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["team", "carlyle", "menu", "leadership"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        parent = heading.find_parent("div")
        if parent:
            for p in parent.find_all(["p", "span"]):
                text = p.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    title = text
                    break

        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["ceo", "chairman", "founder", "co-founder"]):
                role = "partner"
            elif "partner" in title_lower or "managing director" in title_lower:
                role = "partner"
            elif "director" in title_lower or "principal" in title_lower:
                role = "director"
            elif any(r in title_lower for r in ["manager", "head"]):
                role = "manager"
            elif any(r in title_lower for r in ["associate", "analyst", "vice president"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Carlyle press releases.

    Structure: article.node--type-press-release contains:
    - h3 (title)
    - time[datetime] (ISO 8601 date)
    - a[href] (link to full article)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find press release articles only
    for article in soup.find_all("article"):
        classes = article.get("class", [])
        if not isinstance(classes, list) or "node--type-press-release" not in classes:
            continue

        # Extract title from h3
        h3 = article.find("h3")
        if not h3:
            continue

        title = h3.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Extract URL from link
        url = None
        link = article.find("a", href=True)
        if link:
            href = link.get("href", "")
            url = urljoin(base_url, href)

        # Extract date from time element (prefer datetime attribute)
        date = None
        time_elem = article.find("time")
        if time_elem:
            # Use datetime attribute if available (ISO 8601 format)
            datetime_attr = time_elem.get("datetime")
            if datetime_attr:
                # Parse ISO 8601: 2026-02-02T13:00:00Z → 2026-02-02
                date = datetime_attr.split("T")[0]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.90,  # High confidence - structured press releases
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
