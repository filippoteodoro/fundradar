"""Site-specific extractors for pm-partners.it (PM&Partners SGR)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "pm-partners.it"



# URL paths for monitoring — verified 2026-02-23
URLS = {
    "portfolio": "/investimenti/",
    "team": "/chi-siamo/",
    "news": None,  # Site has no news page
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from PM&Partners investments page.

    Companies are in .card-portfolio containers with links to /investimenti/{slug}/.
    Status is indicated by badge text: "In Portafoglio" or "Ceduta".
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Pattern: card-portfolio containers with links
    for card in soup.select(".card-portfolio"):
        # Get the link to company detail page
        link = card.select_one("a[href*='/investimenti/']")
        if not link:
            continue

        href = link.get("href", "")
        if not href or href.endswith("/investimenti/"):
            continue  # Skip main page link

        # Extract company name from URL slug
        slug = href.rstrip("/").split("/")[-1]
        if not slug or slug == "investimenti":
            continue

        # Convert slug to proper name
        name = slug.replace("-", " ").title()

        if not name or len(name) < 2 or name.lower() in seen_names:
            continue

        seen_names.add(name.lower())

        # Determine status from explicit badge element (structural indicator)
        status = "current"
        badge = card.select_one(".card-badge span, .taxonomy-list span")
        if badge:
            badge_text = badge.get_text(strip=True).lower()
            # Check for explicit badge values (this is a labeled UI element)
            if badge_text in ("ceduta", "ceduto", "exited", "disinvestimento", "divested"):
                status = "exited"
            elif badge_text in ("in portafoglio", "current", "attivo", "portfolio"):
                status = "current"

        # Get detail URL
        detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": None,
            "website": detail_url,
            "description": None,
            "status": status,
            "confidence": 0.85,
        })

    # Strategy 2: Fallback - look for any links to /investimenti/{slug}/
    if not companies:
        for link in soup.find_all("a", href=re.compile(r"/investimenti/[^/]+/?$")):
            href = link.get("href", "")
            slug = href.rstrip("/").split("/")[-1]
            if slug and slug != "investimenti" and len(slug) > 1:
                # Skip navigation page slugs
                if slug in ("chi-siamo", "contatti", "team", "news", "storia", "about", "privacy"):
                    continue
                name = slug.replace("-", " ").title()
                if name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": urljoin(base_url, href),
                        "description": None,
                        "status": "current",  # Default for single-section page
                        "confidence": 0.70,
                    })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from PM&Partners team page.

    Team members are in modal triggers with data-bs-* attributes:
    - data-bs-name: Person's name
    - data-bs-role: Job title
    - data-bs-attachment: Photo URL
    - data-bs-linkedin: LinkedIn URL
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Pattern: Modal trigger links with data-bs attributes
    for link in soup.select("a[data-bs-name]"):
        name = link.get("data-bs-name", "").strip()
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue

        seen_names.add(name.lower())

        # Extract title/role
        title = link.get("data-bs-role", "").strip() or None

        # Extract photo URL
        photo_url = link.get("data-bs-attachment", "").strip() or None
        if photo_url:
            photo_url = urljoin(base_url, photo_url)

        # Extract LinkedIn URL
        linkedin = link.get("data-bs-linkedin", "").strip() or None
        if linkedin and "linkedin.com" not in linkedin:
            linkedin = None

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "managing partner" in title_lower or "founding partner" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower or "direttore" in title_lower:
                role = "director"
            elif "principal" in title_lower:
                role = "principal"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower or "analista" in title_lower:
                role = "analyst"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.95,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from PM&Partners news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Look for news/article items
    for article in soup.select("article, .news-item, .post"):
        title_el = article.select_one("h2 a, h3 a, h4 a, .entry-title a")
        if not title_el:
            title_el = article.select_one("h2, h3, h4, .entry-title")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Extract URL
        url = None
        if title_el.name == "a":
            url = title_el.get("href")
        else:
            link = article.select_one("a[href]")
            if link:
                url = link.get("href")
        if url:
            url = urljoin(base_url, url)

        # Extract date
        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
