"""Site-specific extractors for mcpinvest.com (Mindful Capital).

MCP uses WPBakery Visual Composer with hoverbox cards for portfolio companies.
Each hoverbox contains company name, status, industry, and investment type.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "mcpinvest.com"



# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio-mcp/",
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from MCP portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Companies are in vc-hoverbox-wrapper containers
    for hoverbox in soup.select("div.vc-hoverbox-wrapper"):
        # Get company name from h2
        h2 = hoverbox.select_one("h2")
        if not h2:
            continue

        name = h2.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get status and industry from p tag
        # MCP uses structured field format: "Status: X | Industry: Y | Type of investment: Z"
        status = "current"
        sector = None
        investment_type = None

        p_tag = hoverbox.select_one("p")
        if p_tag:
            # Use separator to parse fields properly
            text = p_tag.get_text(separator="|", strip=True)

            # Extract status - look for explicit status field pattern
            # Format is typically "Status:|Divested" or "Status:|In portfolio"
            status_match = re.search(r"Status:?\|([^|]+)", text)
            if status_match:
                status_value = status_match.group(1).strip().lower()
                if status_value in ("divested", "exited", "sold"):
                    status = "exited"
                elif status_value in ("in portfolio", "current", "active"):
                    status = "current"

            # Extract industry/sector - stops at "Type of"
            industry_match = re.search(r"Industry:?\|([^|]+?)(?:\|Type|\|$|$)", text)
            if industry_match:
                sector = industry_match.group(1).strip()

            # Extract investment type for description
            type_match = re.search(r"Type of invest(?:ment|men):?\|([^|]+)", text)
            if type_match:
                investment_type = type_match.group(1).strip()

        # Get detail page link
        website = None
        link = hoverbox.select_one('a[href*="/portfolio/"]')
        if link:
            website = urljoin(base_url, link.get("href", ""))

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": investment_type,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members - not implemented for this site."""
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/press items from Mindful Capital press review page.

    Structure:
    - .vc_grid-item contains each press item
    - h4 has the headline
    - a[href] has the detail page URL
    - No visible dates on listing page
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select(".vc_grid-item"):
        # Get title from h4
        title_el = item.select_one("h4")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL from link
        url = None
        link = item.select_one("a[href]")
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        # No dates visible on listing page
        date = None

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
