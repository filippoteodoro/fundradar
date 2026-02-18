"""Site-specific extractors for bu-partners.com (BU Partners).

Note: Domain changed from www.bu-partners.it to www.bu-partners.com (301 redirect).
Requires headless browser (Playwright) via domain_policies.json.

BU Partners is a European private equity firm with Italian presence.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.bu-partners.com"

# URL paths for monitoring - verified Feb 2026
# Note: domain changed from .it to .com, portfolio from /portfolio to /investments/
URLS = {
    "portfolio": "/investments/",
    "team": "/team/",
    "news": "/news/",
}

# Known person names to exclude from portfolio (team members on homepage)
_PERSON_NAMES = {
    "andreas feith", "alex joergens", "ludovica giovannini",
    "andrea valdesalici", "millie ormescher", "julian popov",
    "erik damgaard", "markus schyboll", "patrick theobald",
    "tony quinlan", "walter meyer", "dirk röhrborn",
}

_SKIP_LOWER = {
    "bu partners", "portfolio", "menu", "investments", "approach",
    "solutions", "about", "team", "news", "contact", "careers",
    "about bu", "our values", "sustainability", "investor login",
}


def _looks_like_person_name(name: str) -> bool:
    """Check if a name looks like a person name (2-3 title-cased words)."""
    words = name.split()
    if len(words) < 2 or len(words) > 4:
        return False
    # Person names: each word is capitalized, no all-caps words
    if all(w[0].isupper() and not w.isupper() for w in words if len(w) > 1):
        # Additional check: no common company suffixes
        lower = name.lower()
        if not any(s in lower for s in ["group", "software", "gmbh", "srl", "spa", "ltd"]):
            return True
    return False


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from BU Partners investments page.

    Structure (verified Feb 2026):
    - Portfolio companies: SYSTABUILD Software Group, Relatech, eGroup,
      Onlineprinters, synava
    - Cards may contain company logos and descriptions
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for company cards/items
    for item in soup.select(".portfolio-item, .company-card, article, .card"):
        name_el = item.select_one("h2, h3, h4, .name, .title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2 or len(name) > 80:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        if name_lower in _SKIP_LOWER:
            continue
        if name_lower in _PERSON_NAMES:
            continue
        seen_names.add(name_lower)

        website = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "bu-partners" not in href.lower():
                website = href

        sector = None
        sector_el = item.select_one(".sector, .category, .industry")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        description = None
        desc_el = item.select_one("p, .description, .summary")
        if desc_el:
            description = desc_el.get_text(strip=True)[:300]

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": 0.85,
        })

    # Fallback: links to /investments/{slug}/ detail pages
    if not companies:
        for link in soup.find_all("a", href=re.compile(r"/investments/[a-z]", re.I)):
            href = link.get("href", "")
            slug = href.rstrip("/").split("/")[-1]
            if not slug or slug in ("investments", "approach", "solutions"):
                continue

            name = None
            heading = link.find(["h2", "h3", "h4", "h5"])
            if heading:
                name = heading.get_text(strip=True)
            if not name:
                name = slug.replace("-", " ").title()

            if not name or len(name) < 2:
                continue

            name_lower = name.lower()
            if name_lower in seen_names or name_lower in _SKIP_LOWER:
                continue
            if name_lower in _PERSON_NAMES:
                continue
            seen_names.add(name_lower)

            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.80,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from BU Partners team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".team-member, .person, article"):
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or len(name.split()) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        if any(skip in name_lower for skip in ["team", "bu partners"]):
            continue

        title = None
        title_el = item.select_one(".title, .role, .position, p")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

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
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.80,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from BU Partners news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select(".news-item, article, .card"):
        heading = item.select_one("h2, h3, h4, a")
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        if any(skip in title_lower for skip in ["all news", "view more"]):
            continue

        url = None
        link = item.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and not href.startswith("javascript"):
                url = urljoin(base_url, href)

        date = None
        date_el = item.select_one("time, .date, [datetime]")
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
