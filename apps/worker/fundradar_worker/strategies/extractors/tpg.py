"""Site-specific extractors for www.tpg.com (TPG).

TPG is a global alternative asset management firm (~$303B AUM, HQ San Francisco)
with platforms spanning Capital, Growth, Impact, Credit, Real Estate, and Market
Solutions. Italian activity includes a Milan office and deals such as the Nexi
digital banking bid and Footballco/Calciomercato.com.

News page at /news-and-insights/news shows press releases. Portfolio page at
/portfolio lists companies across platforms. Site is Next.js with GraphQL data
embedded in __NEXT_DATA__ or Flight Protocol chunks.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import re

DOMAIN = "www.tpg.com"

URLS = {
    "portfolio": "/portfolio",
    "team": None,
    "news": "/news-and-insights/news",
}


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press releases from TPG news page.

    TPG uses Next.js with server-side rendering. News items are embedded
    in the initial HTML via React Flight Protocol data chunks.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    # Try to extract from Next.js Flight Protocol data
    for script in soup.select("script"):
        text = script.string or ""
        if "self.__next_f.push" not in text:
            continue
        # Look for news item patterns in the serialized data
        # Titles appear as strings in the Flight data
        for match in re.finditer(
            r'"uri"\s*:\s*"(/news-and-insights/[^"]+)".*?"date"\s*:\s*"([^"]+)".*?"title"\s*:\s*"([^"]+)"',
            text, re.DOTALL
        ):
            uri, date, title = match.groups()
            if title in seen or len(title) < 10:
                continue
            seen.add(title)

            news.append({
                "title": title,
                "url": urljoin(base_url, uri),
                "date": date[:10] if date else None,
                "summary": None,
                "confidence": 0.85,
            })

    # Fallback: parse rendered HTML
    if not news:
        for article in soup.select("article, .wp-block-post, a[href*='/news-and-insights/']"):
            heading = article.select_one("h2, h3, h4")
            if not heading:
                # If the element is an <a> with text, use it directly
                if article.name == "a":
                    title = article.get_text(strip=True)
                    href = article.get("href", "")
                else:
                    continue
            else:
                title = heading.get_text(strip=True)
                link = article.select_one("a[href]")
                href = link.get("href", "") if link else ""

            if not title or len(title) < 10 or title.lower() in seen:
                continue
            if title.lower() in ("news", "press releases", "insights", "load more"):
                continue
            seen.add(title.lower())

            url = urljoin(base_url, href) if href else None

            date = None
            time_el = article.select_one("time, [datetime]")
            if time_el:
                date = time_el.get("datetime") or time_el.get_text(strip=True)

            news.append({
                "title": title,
                "url": url,
                "date": date,
                "summary": None,
                "confidence": 0.80,
            })

    return news


_STATUS_MAP = {
    "active": "current",
    "realized": "exited",
    "exited": "exited",
    "partially realized": "current",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from TPG /portfolio page.

    Data is embedded in Next.js Flight Protocol chunks (self.__next_f.push).
    Each company has title, slug, sectors, geographies, platforms, statuses.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Collect all Flight Protocol data
    flight_text = ""
    for script in soup.select("script"):
        text = script.string or ""
        if "self.__next_f.push" in text:
            flight_text += text

    # Extract portfolio items from Flight data
    # Pattern: "slug":"company-slug","title":"Company Name" with surrounding fields
    for match in re.finditer(
        r'"slug"\s*:\s*"([^"]+)"\s*,\s*"title"\s*:\s*"([^"]+)"',
        flight_text,
    ):
        slug, title = match.groups()
        # Skip non-portfolio slugs
        if "/" in slug or len(title) < 2:
            continue
        name_lower = title.lower()
        if name_lower in seen:
            continue
        seen.add(name_lower)

        # Extract surrounding context for this item (500 chars after match)
        start = match.start()
        context = flight_text[start:start + 2000]

        # Sectors
        sector = None
        sector_match = re.search(r'"sectors"\s*:\s*\[.*?"name"\s*:\s*"([^"]+)"', context)
        if sector_match:
            sector = sector_match.group(1)

        # Status
        status = None
        status_match = re.search(r'"statuses"\s*:\s*\[.*?"name"\s*:\s*"([^"]+)"', context)
        if status_match:
            status = _STATUS_MAP.get(status_match.group(1).lower())

        # Geography
        hq = None
        geo_match = re.search(r'"geographies"\s*:\s*\[.*?"name"\s*:\s*"([^"]+)"', context)
        if geo_match:
            hq = geo_match.group(1)

        # Description from content field (HTML stripped)
        description = None
        desc_match = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', context)
        if desc_match:
            raw = desc_match.group(1).encode().decode("unicode_escape", errors="ignore")
            raw = re.sub(r"<[^>]+>", " ", raw).strip()
            raw = re.sub(r"\s+", " ", raw)
            if len(raw) > 10:
                description = raw[:500]

        url = urljoin(base_url, f"/portfolio/{slug}")

        companies.append({
            "name": title,
            "url": url,
            "sector": sector,
            "status": status,
            "description": description,
            "hq_country": hq,
            "confidence": 0.95,
        })

    # Fallback: parse rendered HTML cards
    if not companies:
        for card in soup.select("a[href*='/portfolio/']"):
            href = card.get("href", "")
            name = card.get_text(strip=True)
            if not name or len(name) < 2 or name.lower() in seen:
                continue
            if name.lower() in ("portfolio", "view all", "load more", "filter"):
                continue
            seen.add(name.lower())
            companies.append({
                "name": name,
                "url": urljoin(base_url, href),
                "confidence": 0.80,
            })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
