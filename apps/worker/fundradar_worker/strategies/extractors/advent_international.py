"""Site-specific extractors for adventinternational.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.adventinternational.com"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/investments/",
    "team": "/our-team/",
    "news": "/news/",
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Advent International team page.

    Structure:
    - <a href="[profile]"><img><h3>[Name]</h3>[Title/Location]</a>
    - Uses wp-block-advent-content-selector
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all h3 elements that might contain names
    for h3 in soup.find_all("h3"):
        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Check if it looks like a person name (contains at least 2 words)
        parts = name.split()
        if len(parts) < 2:
            continue

        # Skip non-name headings
        if any(skip in name.lower() for skip in [
            "advent", "team", "meet", "work", "filter", "result",
            "contact", "about", "investment", "sector"
        ]):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find parent container (usually the anchor link)
        link = h3.find_parent("a")
        parent = link or h3.find_parent(["div", "article", "li"])

        # Look for title/location in text after the name
        title = None
        if parent:
            # Get text content and try to extract title
            full_text = parent.get_text(" ", strip=True)
            if name in full_text:
                after_name = full_text.split(name, 1)[-1].strip()
                if after_name and len(after_name) < 100:
                    title = after_name

        # Extract photo
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["partner", "managing director", "chairman"]):
                role = "partner"
            elif any(r in title_lower for r in ["director", "head"]):
                role = "director"
            elif any(r in title_lower for r in ["principal", "vice president"]):
                role = "manager"
            elif any(r in title_lower for r in ["associate", "analyst"]):
                role = "associate"

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

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Advent investments page.

    Structure: article.c-card-investment-directory contains:
    - h3: company name
    - .c-card__date: investment date
    - .wp-block-advent-accordion-item__body p: description
    - a.c-related-topic[href*='sectors']: sector link
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Use the specific investment directory card class
    for article in soup.select("article.c-card-investment-directory"):
        # Get company name from h3
        h3 = article.select_one("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract sector from topics links
        sector = None
        sector_link = article.select_one("a.c-related-topic[href*='/sectors/']")
        if sector_link:
            sector = sector_link.get_text(strip=True)

        # Extract description from accordion body
        description = None
        desc_el = article.select_one(".wp-block-advent-accordion-item__body p")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,  # Actual company websites not available on listing
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Advent International news page.

    Structure: <a href="/news/[slug]/"> wrapping <h3> title and <time> date.
    Cards are anchor tags, not article/div elements.
    """
    import re
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Strategy 1: Find <a> card links to /news/ articles
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        # Match individual news article links
        if not href.startswith("/news/") and "/news/" not in href:
            continue
        # Skip the listing page itself
        if href.rstrip("/") == "/news" or href.rstrip("/").endswith("/news"):
            continue

        # Get title from h3 inside the link
        h3 = link.find("h3")
        title = h3.get_text(strip=True) if h3 else None

        if not title or len(title) < 10:
            continue

        # Skip non-news headings
        title_lower = title.lower()
        if any(skip in title_lower for skip in ["filter", "contact", "about us"]):
            continue

        title_key = title_lower[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        url = urljoin(base_url, href)

        # Get date from <time> element inside the link
        date = None
        time_el = link.find("time")
        if time_el:
            date_text = time_el.get("datetime") or time_el.get_text(strip=True)
            if date_text:
                # Try Month DD, YYYY format
                date_match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", date_text)
                if date_match:
                    month_name, day, year = date_match.groups()
                    month_num = _MONTH_NAMES.get(month_name.lower(), "01")
                    if month_num:
                        date = f"{year}-{month_num}-{day.zfill(2)}"
                elif re.match(r"\d{4}-\d{2}-\d{2}", date_text):
                    date = date_text[:10]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Strategy 2: Fallback - find article/div elements with card/news classes
    if not news:
        for article in soup.find_all(["article", "div"], class_=lambda x: x and any(c in str(x).lower() for c in ["card", "post", "news", "item", "tile"])):
            heading = article.find(["h2", "h3", "h4"])
            title = heading.get_text(strip=True) if heading else None

            if not title or len(title) < 10:
                continue

            title_key = title.lower()[:50]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            url = None
            a = article.find("a", href=True)
            if a:
                href = a.get("href", "")
                if href and not href.startswith("#"):
                    url = urljoin(base_url, href)

            date = None
            time_el = article.find("time")
            if time_el:
                date = time_el.get("datetime") or time_el.get_text(strip=True)
            else:
                text = article.get_text(" ", strip=True)
                date_match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
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
                "confidence": 0.80,
            })

    return news

EXTRACTORS = {
    "team": extract_team,
    "portfolio": extract_portfolio,
    "news": extract_news,
}
