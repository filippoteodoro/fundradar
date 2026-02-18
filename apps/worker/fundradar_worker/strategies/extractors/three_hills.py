"""Site-specific extractors for threehills.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.threehills.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio-list/",
    "team": "/people/",
    "news": "/media/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Three Hills portfolio page.

    Structure:
    - Container: .card-item (with class portoflio-item, note typo)
    - Name: h3.title a
    - Description: .wysiwyg p
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find portfolio cards
    for item in soup.select(".card-item"):
        # Check if it's a portfolio item
        item_class = " ".join(item.get("class", []))
        if "portoflio" not in item_class and "portfolio" not in item_class:
            continue

        # Get name from h3.title
        h3 = item.select_one("h3.title")
        if not h3:
            continue

        # Get name from link or direct text
        link = h3.find("a")
        if link:
            name = link.get_text(strip=True)
            website = urljoin(base_url, link.get("href", ""))
        else:
            name = h3.get_text(strip=True)
            website = None

        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get description
        description = None
        wysiwyg = item.select_one(".wysiwyg p")
        if wysiwyg:
            description = wysiwyg.get_text(strip=True)

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Three Hills people page.

    Structure:
    - Name: h3.title
    - Title: .wysiwyg p (following name in content)
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all h3.title elements for names
    for h3 in soup.select("h3.title"):
        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Check if this looks like a person name (has at least 2 parts)
        parts = name.split()
        if len(parts) < 2:
            continue

        # Skip non-name text
        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "partner", "director", "manager", "associate", "analyst",
            "ceo", "cfo", "advisor", "three hills"
        ]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from following .wysiwyg p
        title = None
        next_wysiwyg = h3.find_next_sibling("div", class_="wysiwyg")
        if next_wysiwyg:
            p = next_wysiwyg.find("p")
            if p:
                title = p.get_text(strip=True)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "founder" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "managing director" in title_lower:
                role = "director"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "senior associate" in title_lower:
                role = "associate"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "associate"
            elif "advisor" in title_lower:
                role = "advisor"
            elif "operating partner" in title_lower:
                role = "advisor"

        # Get photo URL from img with matching alt
        photo_url = None
        img = soup.find("img", alt=re.compile(re.escape(name.split()[0]), re.I))
        if img:
            src = img.get("src") or img.get("data-src")
            if src and not src.endswith(".svg"):
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Three Hills media page.

    Structure:
    - Container: .card-item (with news-item class)
    - Title: h3.title a
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find news cards
    for item in soup.select(".card-item"):
        item_class = " ".join(item.get("class", []))
        if "news" not in item_class and "media" not in item_class:
            continue

        h3 = item.select_one("h3.title")
        if not h3:
            continue

        link = h3.find("a")
        if link:
            title = link.get_text(strip=True)
            url = urljoin(base_url, link.get("href", ""))
        else:
            title = h3.get_text(strip=True)
            url = None

        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get date from time element or meta
        date = None
        time_el = item.find("time")
        if time_el:
            date = time_el.get("datetime") or time_el.get_text(strip=True)

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
