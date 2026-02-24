"""Site-specific extractors for smart-capital.it."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.smart-capital.it"



# URL paths for monitoring — verified 2026-02-23
URLS = {
    "portfolio": None,
    "team": "/team/",
    "news": "/media",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Smart Capital.

    Note: Smart Capital's website does not publicly list portfolio companies.
    The investments page only describes their investment strategy (Minority PE, PIPE, etc.)
    without naming specific investee companies.
    """
    # This site does not publish a portfolio listing
    # Returning empty list as there are no extractable companies
    return []


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Smart Capital team page.

    Structure: Carousel with .brxe-yrrhot cards, .brxe-heading names, .brxe-text-basic titles.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for team member cards with Bricks Builder classes
    for card in soup.find_all(class_=re.compile(r"brxe-yrrhot|team-card|team-member", re.I)):
        # Get name from .brxe-heading or h3
        name_el = card.find(class_="brxe-heading") or card.find(["h3", "h4"])
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from .brxe-text-basic or next element
        title = None
        title_el = card.find(class_="brxe-text-basic")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo
        photo_url = None
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Get LinkedIn
        linkedin = None
        for link in card.find_all("a", href=True):
            href = link.get("href", "")
            if "linkedin.com" in href.lower():
                linkedin = href
                break

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["chairman", "ceo", "managing partner"]):
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif any(r in title_lower for r in ["manager", "cfo"]):
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

    # Fallback: look for headings if no Bricks classes found
    if not members:
        for heading in soup.find_all(["h3", "h4"]):
            name = heading.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            words = name.split()
            if len(words) < 2:
                continue

            name_lower = name.lower()
            if any(skip in name_lower for skip in ["team", "smart", "menu"]):
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

            members.append({
                "name": name,
                "title": title,
                "role": None,
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "confidence": 0.80,
            })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract press releases from Smart Capital.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    date_pattern = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["press", "release", "smart capital"]):
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
                d, m, y = match.groups()
                date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

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
