"""Site-specific extractors for reamsgr.it."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.reamsgr.it"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": [
        "/i-fondi-ream/core.html",
        "/i-fondi-ream/residenziale.html",
        "/i-fondi-ream/etico.html",
        "/i-fondi-ream/sanitario.html",
        "/i-fondi-ream/rigenerazione-urbana.html",
    ],
    "team": "/la-societa/chi-siamo-ream.html",
    "news": "/comunicazione/comunicati-e-notizie.html",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract funds from REAM SGR.

    Structure: Fund names organized by category (Core, Residenziale, etc.).
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for fund names in headings and strong elements
    for el in soup.find_all(["h3", "h4", "strong", "a"]):
        name = el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Look for "Fondo" in name
        if "fondo" not in name.lower():
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Determine category/sector
        sector = None
        parent = el.find_parent(["div", "section"])
        if parent:
            parent_text = parent.get_text(strip=True).lower()
            if "core" in parent_text:
                sector = "Core"
            elif "residenziale" in parent_text or "social housing" in parent_text:
                sector = "Residenziale"
            elif "etico" in parent_text or "green" in parent_text:
                sector = "Etico"
            elif "sanitario" in parent_text or "healthcare" in parent_text:
                sector = "Sanitario"
            elif "rigenerazione" in parent_text:
                sector = "Rigenerazione Urbana"

        # Get link if available
        website = None
        if el.name == "a":
            href = el.get("href", "")
            if href:
                website = urljoin(base_url, href)
        else:
            parent_link = el.find_parent("a", href=True)
            if parent_link:
                website = urljoin(base_url, parent_link.get("href", ""))

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from REAM SGR management page.

    Structure: Names with titles and bio paragraphs.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for strong or heading elements with names
    for el in soup.find_all(["strong", "h3", "h4", "b"]):
        text = el.get_text(strip=True)
        if not text:
            continue

        # Check if it looks like a name with title (e.g., "Oronzo PERRINI - Direttore Generale")
        if " - " in text:
            parts = text.split(" - ", 1)
            name = parts[0].strip()
            title = parts[1].strip() if len(parts) > 1 else None
        else:
            # Check if it's just a name (at least 2 words, capitalized)
            words = text.split()
            if len(words) < 2:
                continue
            name = text
            title = None

        # Validate name
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["ream", "sgr", "management", "direttore", "società"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # If no title yet, look in nearby elements
        if not title:
            parent = el.find_parent("div")
            if parent:
                # Look for role text
                for p in parent.find_all("p"):
                    p_text = p.get_text(strip=True)
                    if any(role in p_text.lower() for role in ["direttore", "manager", "responsabile"]):
                        title = p_text[:100]
                        break

        # Get photo
        photo_url = None
        parent = el.find_parent("div")
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if "direttore generale" in title_lower:
                role = "partner"
            elif "direttore" in title_lower:
                role = "director"
            elif "responsabile" in title_lower:
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
    """
    Extract news from REAM SGR.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Italian date pattern
    date_pattern = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")

    for heading in soup.find_all(["h3", "h4"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        title_lower = title.lower()
        if any(skip in title_lower for skip in ["comunicati", "notizie", "ream"]):
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
