"""Site-specific extractors for p101.it (P101 SGR).

P101 is an Italian VC firm (~€500M AUM, HQ Milan) founded by Andrea Di Camillo.
100+ portfolio companies. Notable exits: Tannico (Campari/LVMH), Musement (TUI),
Musixmatch (TPG). Also operates Prana Ventures (seed platform).

Portfolio at /portfolio/, news at /news-press/latest-news/.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "p101.it"

URLS = {
    "portfolio": "/portfolio/",
    "team": "/about/who-we-are/",
    "news": "/news-press/latest-news/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from P101 portfolio page.

    P101 uses a WordPress image grid with company logos. Company names are
    in the alt attribute of img tags. The page headings (h2) are filter labels
    like "Location", "Industry", "Fund" — NOT company names.
    """
    import re

    # The monitor can call extractors for multiple URL buckets; avoid parsing
    # team/news pages where logo alt text creates portfolio false positives.
    if "/portfolio" not in (base_url or "").lower():
        return []

    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    normalize_map = {
        "2 bauzaar.it": "Bauzaar",
        "depor village": "Deporvillage",
    }
    hard_skip = {
        "location",
        "industry",
        "fund",
        "company",
        "portfolio",
        "all companies",
        "portfolio companies",
        "skip to main content",
        "skip companies list",
        "bynd",
        "civitfun",
        "hotiday",
    }

    # Primary: extract from img alt attributes in portfolio grid
    for img in soup.select("img[alt]"):
        alt = img.get("alt", "").strip()
        if not alt or len(alt) < 2:
            continue

        # Clean common suffixes from alt text
        name = alt
        name = re.sub(r'\s*[-–]\s*logo\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+logo\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[-_ ]logo[-_ ]?[a-z0-9]+$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*[-–]\s*P101\s*$', '', name, flags=re.IGNORECASE)
        name = name.strip()

        key = name.lower()
        if key in normalize_map:
            name = normalize_map[key]
            key = name.lower()

        if not name or len(name) < 2 or name.lower() in seen:
            continue

        # Skip generic alt text, navigation, and non-company names
        skip_patterns = (
            "logo", "icon", "p101", "portfolio", "image", "photo",
            "location", "industry", "fund", "status", "home", "team",
            "news", "contact", "about", "prana", "header", "footer",
            "banner", "background", "arrow", "close", "menu", "search",
        )
        if key in hard_skip or key in skip_patterns:
            continue
        # Skip if alt is just "Logo rgb" or similar generic text
        if re.match(r'^logo', name, re.IGNORECASE):
            continue
        # Reject social/nav artifacts embedded in names (e.g., "Bynd logo1")
        if re.search(r'\b(?:logo|icon|link)\b', key):
            continue
        # Reject hashed/id artifacts and malformed alt blobs
        if re.search(r'\bid[a-z0-9]{6,}\b', key):
            continue
        if key.startswith("connect ventures "):
            continue
        if len(name) > 80:
            continue

        seen.add(name.lower())

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from P101 team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    for item in soup.select(
        ".team-member, .person, .card, article, "
        "[class*='team'], [class*='person']"
    ):
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen:
            continue
        if any(skip in name.lower() for skip in ["team", "about", "contact"]):
            continue
        seen.add(name.lower())

        title = None
        title_el = item.select_one(".title, .position, .role, p")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        linkedin = None
        for a in item.select("a[href*='linkedin']"):
            linkedin = a.get("href")
            break

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from P101 news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen = set()

    for article in soup.select("article, .post, .news-item, .card"):
        title_el = article.select_one("h2, h3, h4, .title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen:
            continue
        seen.add(title.lower())

        url = None
        link = article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        summary = None
        summary_el = article.select_one("p, .excerpt, .summary")
        if summary_el and summary_el != title_el:
            summary = summary_el.get_text(strip=True)[:300]

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
    "team": extract_team,
    "news": extract_news,
}
