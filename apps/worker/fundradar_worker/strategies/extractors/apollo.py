"""Site-specific extractors for www.apollo.com (Apollo).

Apollo is a global alternative asset manager. Their website structure is complex
with multiple strategies (credit, equity, real assets, etc.) rather than a simple
portfolio page. This extractor focuses on press releases and leadership pages.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.apollo.com"

# URL paths for monitoring - verified against live site
# Note: Apollo does NOT publish a browsable portfolio page. Their /strategies page
# is a marketing overview with headings like "Asset Management", "Capital Solutions" etc.
# Portfolio data must come from PEM deals and manual entries.
URLS = {
    "portfolio": None,  # No portfolio page — /strategies is marketing, not a portfolio listing
    "team": "/aboutus/leadership-and-people",
    "news": "/insights-news/pressreleases",
}

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Apollo does not publish a browsable portfolio page.

    Their /strategies page is a marketing overview with section headings like
    "Asset Management", "Capital Solutions", "Retirement Solutions" — these are
    business lines, not portfolio companies. Extracting from this page produces
    only garbage entries.

    Portfolio data for Apollo comes from PEM deals and manual entries in
    portfolio_items.json instead.
    """
    return []

def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract leadership team from Apollo leadership page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for leadership cards/items
    for item in soup.select(".leader-card, .person-card, .team-member, article"):
        # Get name from heading
        name_el = item.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Must have at least 2 words
        if len(name.split()) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip navigation items
        if any(skip in name_lower for skip in ["leadership", "apollo", "team", "menu"]):
            continue

        # Get title
        title = None
        title_el = item.select_one(".title, .role, .position, p")
        if title_el and title_el != name_el:
            title = title_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = item.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["ceo", "chairman", "founder", "co-founder"]):
                role = "partner"
            elif "partner" in title_lower or "managing director" in title_lower:
                role = "partner"
            elif "director" in title_lower or "principal" in title_lower:
                role = "director"
            elif "vice president" in title_lower or "vp" in title_lower:
                role = "manager"

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
    """Extract press releases from Apollo news page.

    Structure: <a> tags with href to /insights-news/pressreleases/YYYY/MM/[slug].
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Strategy 1: CSS class-based selectors
    for item in soup.select(".press-release, .news-item, article, .card"):
        heading = item.select_one("h2, h3, h4, a")
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue

        if any(skip in title_lower for skip in ["press releases", "all news", "see more", "load more"]):
            continue

        seen_titles.add(title_lower)

        url = None
        link = item.find("a", href=True)
        if not link and heading.name == "a":
            link = heading
        if link:
            href = link.get("href", "")
            if href and not href.startswith("javascript"):
                url = urljoin(base_url, href)

        date = None
        date_el = item.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)
        else:
            text = item.get_text()
            date_match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}", text, re.I)
            if date_match:
                date = date_match.group(0)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Strategy 2: Find links by href pattern (press release URLs)
    if not news:
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "/pressreleases/" not in href and "/press-releases/" not in href:
                continue
            # Must have a slug after the date path
            if not re.search(r"/pressreleases/\d{4}/\d{2}/", href) and \
               not re.search(r"/press-releases/", href):
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 15:
                continue

            title_lower = title.lower()
            if any(skip in title_lower for skip in ["press releases", "all news", "see more", "load more"]):
                continue

            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            url = urljoin(base_url, href)

            # Try to find date near the link
            date = None
            parent = link.find_parent(["div", "li", "article"])
            if parent:
                text = parent.get_text(" ", strip=True)
                date_match = re.search(
                    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
                    text, re.I
                )
                if date_match:
                    month_name, day, year = date_match.groups()
                    month_num = _MONTH_NAMES.get(month_name.lower(), "01")
                    if month_num:
                        date = f"{year}-{month_num}-{day.zfill(2)}"

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
