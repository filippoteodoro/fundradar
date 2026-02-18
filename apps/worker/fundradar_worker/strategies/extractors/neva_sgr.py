"""Site-specific extractors for nevasgr.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.nevasgr.com"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/content/neva/en/portfolio.html",
    "team": "/content/neva/en/team.html",
    "news": "/content/neva/en/news.html",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Neva SGR portfolio page.

    Structure: Logo images with company names in alt text or filenames.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for images in the portfolio section
    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = img.get("alt", "").strip()

        # Check if it's a portfolio image
        if "portfolio" not in src.lower() and "investment" not in src.lower():
            continue

        # Get name from alt text or filename
        name = alt
        if not name or name.lower() in ["logo", "image"]:
            # Extract from filename
            filename = src.split("/")[-1]
            name = filename.replace(".webp", "").replace(".png", "").replace(".jpg", "")
            name = name.replace("_", " ").replace("-", " ").strip()

        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from nearby text
        sector = None
        parent = img.find_parent(["a", "div"])
        if parent:
            # Look for category label
            for el in parent.find_all(["p", "span", "div"]):
                text = el.get_text(strip=True)
                if text and len(text) < 30 and text.lower() != name_lower:
                    sector = text
                    break

        # Get website from parent link
        website = None
        parent_link = img.find_parent("a", href=True)
        if parent_link:
            href = parent_link.get("href", "")
            if href.startswith("http") and "nevasgr" not in href.lower():
                website = href

        # Get logo URL
        logo_url = None
        if src:
            logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "logo_url": logo_url,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Neva SGR about page.

    Structure: Profile images with h3 names and p titles.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for h3 elements that are names
    for h3 in soup.find_all("h3"):
        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Basic name check
        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["board", "team", "neva", "menu", "about"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find title from following p element
        title = None
        next_p = h3.find_next_sibling("p")
        if next_p:
            title = next_p.get_text(strip=True)
        else:
            parent = h3.find_parent("div")
            if parent:
                p = parent.find("p")
                if p:
                    title = p.get_text(strip=True)

        # Get photo from nearby image
        photo_url = None
        parent = h3.find_parent("div")
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src")
                if src and "people" in src.lower():
                    photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["chairman", "presidente", "ceo"]):
                role = "partner"
            elif any(r in title_lower for r in ["director", "direttore"]):
                role = "director"
            elif "independent" in title_lower:
                role = "board"

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
    """
    Extract news from Neva SGR.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    date_pattern = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)

    for heading in soup.find_all(["h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["news", "neva", "menu"]):
            continue

        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))

        date = None
        parent = heading.find_parent(["article", "div", "li"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                day, month, year = match.groups()
                months = {
                    "january": "01", "february": "02", "march": "03", "april": "04",
                    "may": "05", "june": "06", "july": "07", "august": "08",
                    "september": "09", "october": "10", "november": "11", "december": "12"
                }
                month_num = months.get(month.lower(), "01")
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
