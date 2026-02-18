"""Site-specific extractors for apheon.com.

Apheon is a European mid-market PE fund (€2.6B AUM).
Portfolio at /investment/ uses JetEngine grid with Elementor.
Companies displayed in cards with sector tags and descriptions.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.apheon.com"


# URL paths — verified against live site
URLS = {
    "portfolio": "/investment/",
    "team": None,
    "news": "/news",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Apheon /investment/ page.

    Structure: JetEngine grid with cards containing:
    - Company name in heading tags (h3/h4/h5)
    - Sector label as text above the name
    - Description paragraph
    - Link to detail page at /investment/{company-slug}/
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Strategy 1: Find links to individual portfolio pages
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        # Match /investment/{slug}/ but not /investment/ itself
        if "/investment/" not in href or href.rstrip("/").endswith("/investment"):
            continue
        # Skip pagination, filters, anchors
        if "?" in href or "#" in href or "page" in href.lower():
            continue

        # Look for company name in heading inside the link or nearby
        name = None
        for tag in ["h3", "h4", "h5", "h2"]:
            el = link.find(tag)
            if el:
                name = el.get_text(strip=True)
                break

        # Also check img alt text as fallback
        if not name:
            img = link.find("img")
            if img and img.get("alt"):
                alt = img["alt"].strip()
                # Skip generic alts
                if len(alt) > 2 and alt.lower() not in ("logo", "image", "photo"):
                    name = alt

        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip non-company text
        if name_lower in ("learn more", "read more", "view all", "investment", "investments"):
            continue

        # Look for sector text
        sector = None
        parent = link.find_parent("div")
        if parent:
            # Sector is often in a separate text element before/above the name
            for el in parent.find_all(["span", "div", "p"], recursive=True):
                text = el.get_text(strip=True)
                if text and text != name and len(text) < 50:
                    if any(kw in text.lower() for kw in [
                        "industrial", "healthcare", "service", "consumer",
                        "technology", "niche", "tech",
                    ]):
                        sector = text
                        break

        # Look for description
        description = None
        if parent:
            for p in parent.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 20 and text.lower() != name_lower:
                    description = text[:500]
                    break

        companies.append({
            "name": name,
            "sector": sector,
            "website": urljoin(base_url, href),
            "description": description,
            "status": "current",
            "confidence": 0.85,
        })

    # Strategy 2: If few results from links, also look for headings not in links
    if len(companies) < 5:
        for heading in soup.find_all(["h3", "h4", "h5"]):
            name = heading.get_text(strip=True)
            if not name or len(name) < 2 or len(name) > 60:
                continue
            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            # Skip navigation/section headers
            if name_lower in ("investment", "investments", "portfolio", "case studies",
                              "learn more", "read more", "our investments"):
                continue
            seen_names.add(name_lower)

            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.75,
            })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/press items from Apheon news page.

    Structure: JetEngine grid items with:
    - h4 headings with <a> tags for titles
    - span.elementor-heading-title inside <a> for dates ("Month DD, YYYY")
    News page: https://www.apheon.com/news
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Date pattern: "Month DD, YYYY" or "ON Month DD, YYYY"
    date_re = re.compile(
        r"(?:ON\s+)?"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),?\s+(\d{4})",
        re.IGNORECASE,
    )

    # Find all h4 headings (news titles)
    for h4 in soup.find_all("h4"):
        # Get title text
        title = h4.get_text(separator=" ", strip=True)
        if not title or len(title) < 20:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Extract URL from link inside h4
        link = h4.find("a")
        url = None
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        # Extract date from nearby elements in the same grid item
        date = None
        parent = h4.find_parent(["div", "article", "li"])
        if parent:
            # Look for date text in span.elementor-heading-title or similar
            for el in parent.find_all(["span", "div", "p"]):
                text = el.get_text(strip=True)
                m = date_re.search(text)
                if m:
                    date = text
                    break

        # No summary available on listing page
        summary = None

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
