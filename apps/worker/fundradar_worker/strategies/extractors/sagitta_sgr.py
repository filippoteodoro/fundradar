"""Site-specific extractors for sagittasgr.it (Sagitta SGR)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.sagittasgr.it"



# URL paths for monitoring - verified against live site
# Sagitta is a real estate/credit fund manager with product pages
URLS = {
    "portfolio": "/prodotti-e-servizi/",
    "team": "/chi-siamo/il-team/",
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract real estate portfolio assets from Sagitta SGR.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for heading in soup.find_all(["h2", "h3", "h4", "strong"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "portafoglio", "sagitta", "menu", "filtri",
            "real estate", "scopri"
        ]):
            continue

        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        website = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            href = parent_link.get("href", "")
            if href and "/portafoglio" in href:
                website = urljoin(base_url, href)

        sector = None
        description = None
        parent = heading.find_parent("div")
        if parent:
            for span in parent.find_all(["span", "p"]):
                text = span.get_text(strip=True)
                if text and len(text) < 100 and text.lower() != name_lower:
                    if any(kw in text.lower() for kw in [
                        "residential", "residenziale", "office", "ufficio",
                        "industrial", "logistics", "mixed", "hotel", "commercial"
                    ]):
                        sector = text
                    elif not description:
                        description = text
                    break

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Sagitta SGR team page.

    Uses card-based layout with h4 names and LinkedIn links.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for heading in soup.find_all(["h4", "h3", "strong"]):
        name = heading.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if any(skip in name_lower for skip in [
            "team", "sagitta", "menu", "scopri",
            "management", "chi siamo"
        ]):
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

        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src and "placeholder" not in src.lower():
                    photo_url = urljoin(base_url, src)

        linkedin = None
        if parent:
            for link in parent.find_all("a", href=True):
                href = link.get("href", "")
                if "linkedin.com" in href.lower():
                    linkedin = href
                    break

        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "cio" in title_lower:
                role = "partner"
            elif any(r in title_lower for r in ["chief", "head"]):
                role = "director"
            elif any(r in title_lower for r in ["fund manager", "senior director"]):
                role = "manager"
            elif any(r in title_lower for r in ["vice fund manager", "manager"]):
                role = "manager"
            elif any(r in title_lower for r in ["senior", "specialist"]):
                role = "associate"
            elif any(r in title_lower for r in ["analyst", "associate", "trainee"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from Sagitta SGR.
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
        if any(skip in title_lower for skip in ["news", "sagitta", "menu"]):
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
