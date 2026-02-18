"""Site-specific extractors for riveancapital.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "riveancapital.com"



# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/investments",
    "team": "/professionals",
    "news": "/news",
}
def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Rivean Capital news page.

    Structure: .item > a containing:
    - h4: title
    - h6: date (DD.MM.YYYY format)
    - href: article URL
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select(".item"):
        link = item.select_one("a")
        if not link:
            continue

        # Extract title
        title_el = link.select_one("h4")
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

        # Extract date
        date = None
        date_el = link.select_one("h6")
        if date_el:
            date = date_el.get_text(strip=True)  # Format: DD.MM.YYYY

        # Extract URL
        url = link.get("href")
        if url:
            url = urljoin(base_url, url)

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
    Extract portfolio companies from Rivean Capital investments page.

    Structure: .portfolio > .item cards with:
    - h5: company name
    - .description p: description
    - a[href*=investments/]: detail page link
    - Classes: current-investments, historical-investments (status)
    - Classes: netherlands, germany, switzerland, etc. (country)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    portfolio = soup.select_one(".portfolio")
    if not portfolio:
        return companies

    for item in portfolio.select(".item"):
        # Get company name from h5
        name_el = item.select_one("h5")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get description from .description p (skip empty p.large)
        description = None
        desc_container = item.select_one(".description")
        if desc_container:
            for p in desc_container.select("p"):
                text = p.get_text(strip=True)
                if text:
                    description = text
                    break

        # Get detail page link
        website = None
        link_el = item.select_one('a[href*="/investments/"]')
        if link_el:
            href = link_el.get("href", "")
            if href:
                website = urljoin(base_url, href)

        # Determine status from classes
        classes = item.get("class", [])
        if "current-investments" in classes:
            status = "current"
        elif "historical-investments" in classes:
            status = "exited"
        else:
            status = "current"  # Default

        # Get country from classes
        country = None
        country_map = {
            "netherlands": "Netherlands",
            "germany": "Germany",
            "switzerland": "Switzerland",
            "belgium": "Belgium",
            "austria": "Austria",
            "france": "France",
            "uk": "United Kingdom",
            "italy": "Italy",
        }
        for c in classes:
            if c in country_map:
                country = country_map[c]
                break

        companies.append({
            "name": name,
            "description": description,
            "website": website,
            "country": country,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Rivean Capital professionals page.

    Structure: Cards with:
    - <a href="[profile]">
    - <h4> for name
    - <h6> for title
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find h4 elements with names
    for h4 in soup.find_all("h4"):
        name = h4.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-name headings
        if any(skip in name.lower() for skip in [
            "team", "professional", "overview", "investment", "contact",
            "news", "menu", "working", "career"
        ]):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Look for title in h6 sibling or nearby element
        title = None
        h6 = h4.find_next_sibling("h6")
        if h6:
            title = h6.get_text(strip=True)

        # If no sibling, check parent container
        if not title:
            parent = h4.find_parent("a") or h4.find_parent(["div", "li"])
            if parent:
                h6 = parent.find("h6")
                if h6:
                    title = h6.get_text(strip=True)

        # Extract profile link
        profile_url = None
        link = h4.find_parent("a")
        if link:
            href = link.get("href", "")
            if href:
                profile_url = urljoin(base_url, href)

        # Extract photo if present
        photo_url = None
        if link:
            img = link.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["senior partner", "partner", "managing director", "founder"]):
                role = "partner"
            elif any(r in title_lower for r in ["director", "head of"]):
                role = "director"
            elif any(r in title_lower for r in ["principal", "vice president", "manager"]):
                role = "manager"
            elif any(r in title_lower for r in ["associate", "analyst", "assistant"]):
                role = "associate"

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


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
