"""Site-specific extractors for alkemiacapital.com (Alkemia SGR)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.alkemiacapital.com"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": "/en/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Alkemia.
    Portfolio (fondi) page lists invested companies.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Look for headings in Elementor structure
    for heading in soup.find_all(["h2", "h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "fondi", "portfolio", "alkemia", "menu", "pipe",
            "venture capital", "private equity", "scopri",
            "informazioni generali", "newsletter", "siamo soci"
        ]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        website = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            href = parent_link.get("href", "")
            if href and "/fondi/" in href:
                website = urljoin(base_url, href)

        description = None
        parent = heading.find_parent("div", class_=re.compile(r"elementor"))
        if parent:
            for p in parent.find_all(["p", "div"]):
                text = p.get_text(strip=True)
                if text and len(text) > 30 and text.lower() != name_lower:
                    description = text[:200]
                    break

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Alkemia team page.

    Structure: Elementor cards with h3 names and icon-list titles.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for h3 elements which contain names
    for heading in soup.find_all("h3", class_=re.compile(r"elementor-heading-title|heading", re.I)):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in ["team", "alkemia", "menu", "fondi"]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from icon-list or nearby elements
        title = None
        parent = heading.find_parent("div", class_=re.compile(r"elementor"))
        if parent:
            # Look for icon-list text
            icon_list = parent.find(class_=re.compile(r"elementor-icon-list-text"))
            if icon_list:
                title = icon_list.get_text(strip=True)
            else:
                for p in parent.find_all(["p", "span"]):
                    text = p.get_text(strip=True)
                    if text and len(text) < 100 and text.lower() != name_lower:
                        title = text
                        break

        # Get photo
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Get LinkedIn
        linkedin = None
        if parent:
            for link in parent.find_all("a", href=True):
                href = link.get("href", "")
                if "linkedin.com" in href.lower():
                    linkedin = href
                    break

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["managing partner", "ceo", "amministratore delegato"]):
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif any(r in title_lower for r in ["director", "cfo", "consigliere"]):
                role = "director"
            elif any(r in title_lower for r in ["analyst", "associate"]):
                role = "associate"
            elif any(r in title_lower for r in ["manager", "business development"]):
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    # Fallback: look for any h3 that looks like a name
    if not members:
        for heading in soup.find_all("h3"):
            name = heading.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            words = name.split()
            if len(words) < 2:
                continue

            name_lower = name.lower()
            if any(skip in name_lower for skip in ["team", "alkemia", "menu"]):
                continue

            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            members.append({
                "name": name,
                "title": None,
                "role": None,
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "confidence": 0.80,
            })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Alkemia.
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
        if any(skip in title_lower for skip in ["news", "alkemia", "menu", "fondi"]):
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
