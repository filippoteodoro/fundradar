"""Site-specific extractors for zestgroup.vc."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "zestgroup.vc"

# URL paths for monitoring — verified 2026-02-23
URLS = {
    "portfolio": "/investments",
    "team": "/en/people",
    "news": "/en/news",
}
_SKIP_LOWER = {
    "about us", "about", "innovation", "people", "content hub", "news",
    "the hub", "thehub", "zest ai", "zest cyber cecurity",
    "zest cyber security", "menu", "cookie", "contact", "login",
    "home", "portfolio", "investments", "management",
}

# Patterns for image filenames and section headers
_GARBAGE_RE = re.compile(
    r"(?:^3d render|^foto sito|^zest header|plexus design|"
    r"shallow depth|copia \d|verticali \d|"
    r"\.(jpg|jpeg|png|gif|svg|webp)$)",
    re.I,
)

# News headline pattern (contains funding round language)
_NEWS_RE = re.compile(
    r"(?:closes?\s+(?:a\s+)?[€$£]|round\s+(?:da|of)\s+[€$£]|"
    r"chiude\s+un\s+round|pre-seed|seed\s+round|series\s+[a-c]\b|"
    r"funding\s+round)",
    re.I,
)

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from ZEST GROUP investments page.

    Structure (verified Feb 2026):
    - div.portfolio-card contains each investment
    - h3 inside card has company name
    - p has description
    - img has logo
    - a links to /en/portfolio/{slug} detail pages
    Also try .c-card / .card__title as fallback (old structure).
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Strategy 1: .portfolio-card (current structure)
    for card in soup.select(".portfolio-card"):
        title_el = card.select_one("h3") or card.select_one("h2, h4")
        if not title_el:
            # Try img alt as name
            img = card.select_one("img")
            if img and img.get("alt"):
                title_el = type('FakeEl', (), {'get_text': lambda self, **kw: img.get("alt", "").strip()})()
            else:
                continue

        name = title_el.get_text(strip=True)
        if not name or len(name) < 2 or len(name) > 60:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        if name_lower in _SKIP_LOWER:
            continue
        if _GARBAGE_RE.search(name):
            continue
        if _NEWS_RE.search(name):
            continue
        seen_names.add(name_lower)

        description = None
        desc_el = card.select_one("p")
        if desc_el:
            description = desc_el.get_text(strip=True)[:300]

        logo_url = None
        img = card.select_one("img")
        if img:
            src = img.get("src")
            if src:
                logo_url = urljoin(base_url, src)

        detail_url = None
        link = card.select_one("a[href*='/portfolio/']")
        if not link:
            link = card.select_one("a[href*='/investments/']")
        if link:
            href = link.get("href")
            if href:
                detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": description,
            "status": "current",
            "detail_url": detail_url,
            "logo_url": logo_url,
            "confidence": 0.90,
        })

    # Strategy 2: .c-card / .card__title (old structure, fallback)
    if not companies:
        for card in soup.select(".c-card"):
            title_el = card.select_one(".card__title")
            if not title_el:
                continue

            name = title_el.get_text(strip=True)
            if not name or len(name) < 2 or len(name) > 60:
                continue

            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            if name_lower in _SKIP_LOWER:
                continue
            if _GARBAGE_RE.search(name):
                continue
            if _NEWS_RE.search(name):
                continue
            seen_names.add(name_lower)

            description = None
            text_el = card.select_one(".card__text p")
            if text_el:
                description = text_el.get_text(strip=True)[:300]

            companies.append({
                "name": name,
                "sector": None,
                "website": None,
                "description": description,
                "status": "current",
                "confidence": 0.90,
            })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Zest Group team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for heading in soup.find_all(["h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["team", "people", "zest", "menu", "about"]):
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

        linkedin = None
        if parent:
            for link in parent.find_all("a", href=True):
                href = link.get("href", "")
                if "linkedin.com" in href.lower():
                    linkedin = href
                    break

        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["ceo", "founder", "founding"]):
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif any(r in title_lower for r in ["principal", "manager"]):
                role = "manager"
            elif any(r in title_lower for r in ["associate", "analyst"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Zest Group.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    date_pattern = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", re.I)

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["news", "zest", "menu"]):
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))

        date = None
        parent = heading.find_parent(["article", "div"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                month, day, year = match.groups()
                month_num = _MONTH_NAMES.get(month.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.75,
        })

    return news

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
