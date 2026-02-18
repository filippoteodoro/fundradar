"""Site-specific extractors for clarisventures.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.clarisventures.com"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/portfolio/",
    "team": "/team/",
    "news": "/news/",
}
def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Claris Ventures news page.

    Structure: article.eael-timeline-post with:
    - a.eael-timeline-post-link: wraps entire content including title and link
    - h2: title
    - time: date (Italian format)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for article in soup.select("article.eael-timeline-post"):
        # Extract title
        h2 = article.select_one("h2")
        if not h2:
            continue

        title = h2.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Extract URL from wrapper link
        url = None
        link = article.select_one("a.eael-timeline-post-link")
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        # Extract date
        date = None
        time_el = article.select_one("time")
        if time_el:
            date = time_el.get("datetime") or time_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Claris Ventures portfolio page.

    Structure:
    - div.gallery-item-caption-over contains each company
    - h2.fg-item-title has company name
    - div.fg-item-content p has description
    - Links to company website
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for item in soup.select(".gallery-item-caption-over"):
        # Get name from h2.fg-item-title
        h2 = item.select_one("h2.fg-item-title")
        if not h2:
            continue

        name = h2.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get description from fg-item-content p
        description = None
        content = item.select_one(".fg-item-content p")
        if content:
            description = content.get_text(strip=True)

        # Get website from link
        website = None
        link = item.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href.startswith("http") and "clarisventures" not in href:
                website = href

        companies.append({
            "name": name,
            "sector": "Life Sciences",  # Claris Ventures focuses on life sciences
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Claris Ventures team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for team member cards
    for item in soup.select(".eael-team-member"):
        # Get name
        name_el = item.select_one(".eael-team-member-name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title
        title = None
        title_el = item.select_one(".eael-team-member-position")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = item.select_one("img")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Get LinkedIn
        linkedin = None
        li_link = item.select_one("a[href*='linkedin']")
        if li_link:
            linkedin = li_link.get("href")

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "founder" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
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


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
