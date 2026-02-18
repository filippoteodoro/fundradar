"""Site-specific extractors for tscawsgr.com (TeamSystem Capital at Work SGR)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging

DOMAIN = "www.tscawsgr.com"


# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/it/management",
    "news": "/it/en/news",
}
logger = logging.getLogger(__name__)


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Capital@Work SGR team page.

    Structure:
    - img with alt containing name
    - h3 with name
    - p with title/role
    - a with LinkedIn link
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Pattern 1: Look for h3 headings followed by p (title)
    for h3 in soup.select("h3"):
        name = h3.get_text(strip=True)

        # Filter: must look like a person name
        if not name:
            continue
        words = name.split()
        if len(words) < 2 or len(words) > 4:
            continue
        if not all(w[0].isupper() for w in words if len(w) > 2):
            continue
        # Skip navigation/section headers
        if any(skip in name.lower() for skip in ["team", "chi siamo", "contatti", "menu"]):
            continue
        if name in seen_names:
            continue

        # Look for title in next sibling paragraph
        title = None
        next_el = h3.find_next_sibling()
        if next_el and next_el.name == "p":
            title = next_el.get_text(strip=True)
            if len(title) > 200:
                title = title[:200]

        # Look for role in surrounding container
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "amministratore delegato" in title_lower:
                role = "partner"
            elif "coo" in title_lower or "chief operating" in title_lower:
                role = "partner"
            elif "manager" in title_lower or "investment manager" in title_lower:
                role = "investment_manager"
            elif "senior" in title_lower:
                role = "senior"
            elif "officer" in title_lower:
                role = "officer"

        # Look for LinkedIn - check parent container
        linkedin = None
        parent = h3.parent
        if parent:
            for link in parent.select("a[href*='linkedin']"):
                href = link.get("href", "")
                if href and "linkedin.com" in href:
                    linkedin = href
                    break

        # Look for photo
        photo_url = None
        if parent:
            img = parent.select_one("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        seen_names.add(name)
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
    Extract press items from TeamSystem Capital@Work SGR press page.

    Structure:
    - Container: div.press
    - Each item: div.row
      - Source: div.col-md-3.nome
      - Title: div.col-md-7.text
      - Link: div.col-md-2.cta > a (PDF or external link)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find the press container
    press_div = soup.find("div", class_="press")
    if not press_div:
        return news

    # Each press item is a div.row
    for row in press_div.find_all("div", class_="row"):
        # Get source name from col-md-3.nome
        source = None
        source_el = row.find("div", class_="nome")
        if source_el:
            source = source_el.get_text(strip=True)

        # Get title from col-md-7.text
        title_el = row.find("div", class_="text")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Combine source and title if available
        if source and source not in title:
            full_title = f"{source}: {title}"
        else:
            full_title = title

        # Get URL from col-md-2.cta > a
        url = None
        cta_div = row.find("div", class_="cta")
        if cta_div:
            link = cta_div.find("a", href=True)
            if link:
                href = link.get("href")
                url = urljoin(base_url, href)

        news.append({
            "title": full_title,
            "url": url,
            "date": None,  # No dates visible on the page
            "summary": None,
            "confidence": 0.85,
        })

    logger.info(f"Extracted {len(news)} press items from TeamSystem Capital@Work")
    return news


EXTRACTORS = {
    "team": extract_team,
    "news": extract_news,
}
