"""
TEMPLATE: Site-specific extractors for {domain}.

Copy this file and rename to {fund_id}.py (e.g., permira.py)

Instructions:
1. Set DOMAIN to the exact domain (e.g., "www.permira.com")
2. Set URLS to declare the paths for portfolio/team/news pages
3. Implement extraction functions for portfolio/team/news as needed
4. Export functions in the EXTRACTORS dict
5. Test with: python -c "from fundradar_worker.strategies.extractors.{fund_id} import *; print(EXTRACTORS)"
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# REQUIRED: The domain this extractor handles (must match exactly)
DOMAIN = "example.com"  # Change this!

# REQUIRED: URL paths for each page type (use None if not available)
# IMPORTANT: Verify these paths against the LIVE website before committing!
# Do NOT use generic template paths like /investments or /management — these rarely exist.
# Common real paths: /portfolio, /portafoglio, /investimenti, /our-companies, /chi-siamo, etc.
# Single-page sites: use "/" for homepage sections.
# Can be a string path or list of paths for multiple pages.
URLS = {
    "portfolio": None,  # VERIFY: e.g., "/portfolio/", "/investimenti/", "/"
    "team": None,       # VERIFY: e.g., "/team/", "/chi-siamo/persone/"
    "news": None,       # VERIFY: e.g., "/news/", "/newsroom/"
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from the portfolio page HTML.

    Args:
        html: Raw HTML content of the portfolio page
        base_url: The URL the HTML was fetched from (for resolving relative URLs)

    Returns:
        List of company dicts with keys:
        - name (required): Company name
        - sector: Industry/sector
        - website: Company website URL
        - description: Brief description
        - status: "current" or "exited"
        - confidence: 0.0-1.0 extraction confidence
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Common patterns to look for:
    # - div.portfolio-item, div.company-card, article.investment
    # - li elements in a portfolio grid
    # - table rows with company data
    # - JSON-LD or data attributes

    for item in soup.select("YOUR_SELECTOR_HERE"):  # Change this!
        name_el = item.select_one("NAME_SELECTOR")  # Change this!
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Extract optional fields
        sector = None
        sector_el = item.select_one(".sector, .industry, [data-sector]")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        website = None
        link_el = item.select_one("a[href]")
        if link_el and link_el.get("href", "").startswith("http"):
            website = link_el["href"]

        description = None
        desc_el = item.select_one(".description, .summary, p")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": None,
            "confidence": 0.85,  # Adjust based on extraction quality
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from the team/about page HTML.

    Returns:
        List of member dicts with keys:
        - name (required): Full name
        - title: Job title
        - role: Role category (partner, associate, etc.)
        - linkedin: LinkedIn profile URL
        - email: Email address
        - photo_url: Profile photo URL
        - confidence: 0.0-1.0 extraction confidence
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Common patterns:
    # - div.team-member, div.person-card, article.staff
    # - Cards with photo + name + title
    # - Grids with headshots

    for item in soup.select("YOUR_SELECTOR_HERE"):  # Change this!
        name_el = item.select_one("NAME_SELECTOR")  # Change this!
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Extract title
        title = None
        title_el = item.select_one(".title, .position, .role")
        if title_el:
            title = title_el.get_text(strip=True)

        # Extract LinkedIn
        linkedin = None
        for link in item.select("a[href*='linkedin']"):
            linkedin = link.get("href")
            break

        # Extract photo
        photo_url = None
        img = item.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/press items from the news page HTML.

    Returns:
        List of news dicts with keys:
        - title (required): Article title
        - url: Link to full article
        - date: Publication date (ISO format if possible)
        - summary: Brief excerpt
        - confidence: 0.0-1.0 extraction confidence
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []

    for item in soup.select("YOUR_SELECTOR_HERE"):  # Change this!
        title_el = item.select_one("TITLE_SELECTOR")  # Change this!
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Extract URL
        url = None
        link = item.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Extract date
        date = None
        date_el = item.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        # Extract summary
        summary = None
        summary_el = item.select_one(".summary, .excerpt, p")
        if summary_el:
            summary = summary_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


# REQUIRED: Export the extractors
# Only include functions you actually implemented
EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,  # Remove if not needed
}
