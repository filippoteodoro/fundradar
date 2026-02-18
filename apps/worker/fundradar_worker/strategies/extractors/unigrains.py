"""Site-specific extractors for unigrains.fr (Unigrains)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.unigrains.fr"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/en/fr/equipe",
    "news": "/en/fr/actualites",
}
def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Unigrains news page.

    Structure: div.actualites__content > a containing:
    - h2: title
    - href: article URL
    Note: No dates available on listing page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all news containers
    for container in soup.select("div.actualites__content"):
        link = container.select_one("a")
        if not link:
            continue

        # Extract title
        title_el = link.select_one("h2")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Extract URL
        url = link.get("href")
        if url:
            url = urljoin(base_url, url)

        # No dates available on listing page
        date = None

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Unigrains team page.

    Structure: div.news-item cards with:
    - <strong> for name
    - <p> for title
    - <a href="linkedin.com/..."> for LinkedIn
    - <img> for photo
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find team member cards - they use class "news-item" for team cards
    for item in soup.select("div.news-item"):
        # Extract name from <strong> tag
        name_el = item.select_one("strong")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract title from <p> tag (first one after name)
        title = None
        title_el = item.select_one("p")
        if title_el:
            title = title_el.get_text(strip=True)
            # Skip if it looks like a department label
            if title and title.lower() in ["management", "investment", "strategy", "support"]:
                title = None

        # Extract LinkedIn URL
        linkedin = None
        for link in item.select("a[href*='linkedin']"):
            href = link.get("href", "")
            if "linkedin.com" in href:
                linkedin = href
                break

        # Extract photo URL
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
            if any(r in title_lower for r in ["president", "ceo", "chairman", "managing director"]):
                role = "partner"
            elif any(r in title_lower for r in ["director", "head of"]):
                role = "director"
            elif any(r in title_lower for r in ["manager", "responsabile"]):
                role = "manager"
            elif any(r in title_lower for r in ["analyst", "associate", "assistant"]):
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

    # Fallback: if no members found with news-item, try looking for teams container
    if not members:
        teams_div = soup.select_one("div.teams")
        if teams_div:
            for strong in teams_div.find_all("strong"):
                name = strong.get_text(strip=True)
                if not name or len(name) < 3:
                    continue

                name_lower = name.lower()
                if name_lower in seen_names:
                    continue
                seen_names.add(name_lower)

                # Look for title in next sibling
                title = None
                next_p = strong.find_next_sibling("p")
                if next_p:
                    title = next_p.get_text(strip=True)

                # Look for LinkedIn in parent
                linkedin = None
                parent = strong.find_parent()
                if parent:
                    link = parent.find("a", href=lambda h: h and "linkedin" in h)
                    if link:
                        linkedin = link.get("href")

                members.append({
                    "name": name,
                    "title": title,
                    "role": None,
                    "linkedin": linkedin,
                    "email": None,
                    "photo_url": None,
                    "confidence": 0.75,
                })

    return members


# Note: Portfolio extraction not implemented because the Unigrains website
# displays portfolio companies only as logo images without text names.
# The Strategy page shows logos but company names are embedded in images only.

EXTRACTORS = {
    "team": extract_team,
    "news": extract_news,
}
