"""Site-specific extractors for animaalternative.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "animaalternative.it"



# URL paths for monitoring - verified against live site (site uses /it prefix)
URLS = {
    "portfolio": "/it/investimenti",
    "team": "/it/team",
    "news": None,  # No dedicated news page found
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Anima Alternative investments page.

    Companies are in .bio containers with .name and .text elements.
    Status is indicated by "In portafoglio" or "Disinvestito" in text.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all bio sections which contain company info
    for bio in soup.select(".bio"):
        name_el = bio.select_one(".name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen_names:
            continue

        # Skip team member entries (they don't have investment dates)
        text_el = bio.select_one(".text")
        text_content = text_el.get_text() if text_el else ""

        # Check if this is an investment (has date or status)
        if "Data investimento" not in text_content and "Data d'investimento" not in text_content:
            # Might be team member, not investment
            continue

        seen_names.add(name.lower())

        # Extract description (first paragraph before date)
        description = None
        if text_el:
            paragraphs = text_el.find_all("p")
            if paragraphs:
                # First paragraph is usually description
                description = paragraphs[0].get_text(strip=True)[:500]

        # Determine status - look for explicit status field pattern
        # Format: "Stato: Disinvestito" or similar field-based pattern
        status = "current"
        # Check for explicit status field value (case-insensitive)
        status_match = re.search(r"stato\s*:\s*(disinvestito|in\s*portafoglio|current|exited)", text_content, re.IGNORECASE)
        if status_match:
            status_value = status_match.group(1).lower().strip()
            if status_value in ("disinvestito", "exited"):
                status = "exited"

        companies.append({
            "name": name,
            "sector": None,
            "website": None,
            "description": description,
            "status": status,
            "confidence": 0.90,
        })

    # Strategy 2: Fallback - look for fund links (/it/investimenti/{fund-name})
    if not companies:
        for link in soup.find_all("a", href=re.compile(r"/it/investimenti/[^/]+")):
            href = link.get("href", "")
            slug = href.rstrip("/").split("/")[-1]
            if slug and slug not in ("investimenti", "it") and len(slug) > 2:
                name = slug.replace("-", " ").title()
                if name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": None,
                        "description": None,
                        "status": "current",  # Default for investment funds page
                        "confidence": 0.70,
                    })

    # Strategy 3: Look for any card/item containers with headings
    if not companies:
        for card in soup.find_all(["article", "div"], class_=re.compile(r"card|item|fund|investment", re.I)):
            heading = card.find(["h2", "h3", "h4", "strong"])
            if heading:
                name = heading.get_text(strip=True)
                if (name and len(name) > 2 and len(name) < 100
                    and name.lower() not in seen_names
                    and not any(skip in name.lower() for skip in ["menu", "filter", "cerca", "cookie", "privacy"])):
                    seen_names.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": None,
                        "description": None,
                        "status": None,
                        "confidence": 0.60,
                    })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Anima Alternative team page.

    Uses .portraitCell/.portraitBox containers with .name and .role.
    Also handles .bio sections for team members.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Pattern 1: Text divs with name and role (inside portraitCell or standalone)
    for text_div in soup.select(".text"):
        name_el = text_div.select_one(".name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue

        # Check if there's a role - if not, this is likely a company, not a person
        role_el = text_div.select_one(".role, .roles .role")
        if not role_el:
            continue

        # Check if this looks like a company by looking at following bio
        container = text_div.find_parent()
        bio = None
        if container:
            bio = container.find_next(".bio")
        if bio:
            bio_text = bio.get_text()
            if "Data investimento" in bio_text or "Data d'investimento" in bio_text:
                continue  # This is a company, not a person

        seen_names.add(name.lower())

        # Extract role/title - handle br tags
        title = None
        if role_el:
            # Replace br tags with space
            for br in role_el.find_all("br"):
                br.replace_with(" ")
            title = role_el.get_text(strip=True)
            title = re.sub(r'\s+', ' ', title)  # Normalize whitespace

        # Extract photo - look in parent container
        photo_url = None
        if container:
            img = container.select_one("img.portrait, img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if any(x in title_lower for x in ["presidente", "president", "chair"]):
                role = "partner"
            elif any(x in title_lower for x in ["amministratore delegato", "ceo", "chief executive"]):
                role = "partner"
            elif any(x in title_lower for x in ["head", "responsabile"]):
                role = "director"
            elif any(x in title_lower for x in ["director", "direttore"]):
                role = "director"
            elif any(x in title_lower for x in ["manager"]):
                role = "manager"
            elif any(x in title_lower for x in ["associate"]):
                role = "associate"
            elif any(x in title_lower for x in ["analyst", "analista"]):
                role = "analyst"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    # Pattern 2: Bio sections that are team members (not companies)
    for bio in soup.select(".bio"):
        name_el = bio.select_one(".name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue

        # Check if this is a company (has investment date)
        text_el = bio.select_one(".text")
        text_content = text_el.get_text() if text_el else ""
        if "Data investimento" in text_content or "Data d'investimento" in text_content:
            continue  # Skip companies

        seen_names.add(name.lower())

        members.append({
            "name": name,
            "title": None,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.75,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Anima Alternative media page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Look for news/article items
    for article in soup.select("article, .news-item, .media-item, .post"):
        title_el = article.select_one("h2, h3, h4, .title, a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Extract URL
        url = None
        link = article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Extract date
        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

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
