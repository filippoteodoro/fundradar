"""Site-specific extractors for www.baincapitalprivateequity.com."""
import re
from bs4 import BeautifulSoup

DOMAIN = "www.baincapitalprivateequity.com"


# URL paths for monitoring - verified against live site
# News is on parent baincapital.com domain, not this PE subdomain
URLS = {
    "portfolio": "/portfolio",
    "team": "/people",
    "news": "https://www.baincapital.com/news",  # News on parent domain
}
# Names to skip (branding, navigation, generic, UI elements)
_SKIP_NAMES = {
    "bain capital", "bain capital private equity", "click to open",
    "close", "portfolio", "logo", "share this page", "next", "prev",
    "previous", "back to top", "search", "menu", "home",
    "private equity", "venture capital", "credit", "real estate",
}

# Patterns that indicate garbage, not company names
_GARBAGE_PATTERNS = [
    re.compile(r"\bis (?:a|the|one of)\b", re.I),  # Description text
    re.compile(r"^(?:A\s+)?leading\s+", re.I),      # "A leading provider..."
    re.compile(r"\b(?:provider|retailer|manufacturer|distributor|operator|company|platform)\b", re.I),
    re.compile(r"\b(?:founded|established|headquartered)\b", re.I),
    re.compile(r"\b(?:offers?|provides?|delivers?|enables?|serves?)\b", re.I),
    re.compile(r"\b(?:million|billion|revenue|employees)\b", re.I),
    re.compile(r"^share\s+this\b", re.I),
    re.compile(r"\.(jpg|png|svg|gif)$", re.I),
]


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Bain Capital PE portfolio page.

    Structure (as of Feb 2026):
    - Company logos in <a href="#getTop[ID]"><img alt="Company Name"></a>
    - Company detail sections with industry, region, year follow each logo
    - Content is server-rendered HTML (no JS needed)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    def _is_garbage(text: str) -> bool:
        """Check if text looks like a description rather than a company name."""
        if len(text) > 60:
            return True
        for pattern in _GARBAGE_PATTERNS:
            if pattern.search(text):
                return True
        return False

    # Strategy 1: Anchor links with #getTop pattern containing company logo imgs
    for link in soup.find_all("a", href=re.compile(r"#getTop\d+")):
        img = link.find("img", alt=True)
        if not img:
            continue

        name = img.get("alt", "").strip()
        if not name or len(name) < 2 or len(name) > 80:
            continue

        name_lower = name.lower()
        if name_lower in seen or name_lower in _SKIP_NAMES:
            continue
        if _is_garbage(name):
            continue

        seen.add(name_lower)

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": None,
            "status": "current",
            "confidence": 0.85,
        })

    # Strategy 2: Fallback — any img[alt] inside anchors on the portfolio page
    if not companies:
        for link in soup.find_all("a"):
            img = link.find("img", alt=True)
            if not img:
                continue

            name = img.get("alt", "").strip()
            if not name or len(name) < 2 or len(name) > 80:
                continue

            name_lower = name.lower()
            if name_lower in seen or name_lower in _SKIP_NAMES:
                continue
            if _is_garbage(name):
                continue

            # Skip if alt looks like a filename or icon
            if re.search(r"\.(png|jpg|svg|gif|ico)$", name_lower):
                continue

            seen.add(name_lower)

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
    """Extract news/press releases from Bain Capital news page (baincapital.com/news).

    Structure: Article cards with h3 titles, date text, and category tags.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Month name map for date parsing
    month_map = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
    }

    # Strategy: Look for article cards/items with headings and links
    for card in soup.select("article, .card, .news-item, .press-release, [class*='article'], [class*='news']"):
        heading = card.find(["h2", "h3", "h4"])
        if not heading:
            continue

        title = heading.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        if any(skip in title_lower for skip in ["filter", "search", "all news", "load more"]):
            continue
        seen_titles.add(title_lower)

        # Get link
        url = None
        link = card.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href and "/news/" in href:
                url = href if href.startswith("http") else f"https://www.baincapital.com{href}"

        # Parse date (e.g., "October 6, 2025" or "February 10, 2026")
        date = None
        card_text = card.get_text(" ", strip=True)
        date_match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", card_text)
        if date_match:
            month_name, day, year = date_match.groups()
            month_num = month_map.get(month_name.lower())
            if month_num:
                date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Fallback: look for heading links containing /news/
    if not news:
        for link in soup.find_all("a", href=re.compile(r"/news/")):
            title = link.get_text(strip=True)
            if not title or len(title) < 10 or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            href = link.get("href", "")
            url = href if href.startswith("http") else f"https://www.baincapital.com{href}"
            news.append({
                "title": title,
                "url": url,
                "date": None,
                "summary": None,
                "confidence": 0.80,
            })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
