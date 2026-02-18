"""Site-specific extractors for trilanticeurope.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.trilanticeurope.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/our-investments.html",
    "team": "/our-team.html",
    "news": "/news.html",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Trilantic Europe investments page.

    Structure: div.portfolioPanel with data attributes for company info,
    h2 for name, and nested link for URL.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Sector mapping from data attribute values to readable names
    sector_map = {
        "consumer_and_leisure": "Consumer & Leisure",
        "business_services": "Business Services",
        "industrials_and_energy_transition": "Industrials & Energy Transition",
        "healthcare": "Healthcare",
        "tmt": "TMT",
        "other": "Other",
    }

    # Find all portfolio panels with data-title attribute
    panels = soup.find_all("div", class_="portfolioPanel", attrs={"data-title": True})

    for panel in panels:
        # Get company name from h2 or fallback to data-title
        h2 = panel.find("h2")
        name = h2.get_text(strip=True) if h2 else panel.get("data-title", "")

        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get status from data-realised attribute
        realised_attr = panel.get("data-realised", "").lower()
        if realised_attr in ("realised", "realized"):
            status = "exited"
        elif "partial" in realised_attr:
            status = "partial"
        else:
            status = "current"

        # Get sector from data-sector attribute
        sector_attr = panel.get("data-sector", "")
        sector = sector_map.get(sector_attr, sector_attr.replace("_", " ").title() if sector_attr else None)

        # Get URL from nested link
        link = panel.find("a", href=True)
        href = link.get("href", "") if link else ""
        website = urljoin(base_url, href) if href else None

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": status,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Trilantic Europe team page.

    Structure: Links with h3 names and h4 titles.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for links to team member profiles
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "team" not in href.lower():
            continue

        # Get name from h3
        h3 = link.find("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip navigation items
        name_lower = name.lower()
        if any(skip in name_lower for skip in ["menu", "contact", "home", "news", "portfolio", "about"]):
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from h4
        title = None
        h4 = link.find("h4")
        if h4:
            title = h4.get_text(strip=True)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["managing partner", "senior partner", "founding partner", "partner"]):
                role = "partner"
            elif any(r in title_lower for r in ["managing director", "director"]):
                role = "director"
            elif any(r in title_lower for r in ["principal", "manager"]):
                role = "manager"
            elif any(r in title_lower for r in ["associate", "analyst", "vice president", "vp"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": None,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Trilantic Europe news page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Date pattern
    date_pattern = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})")

    # Look for news article links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "news" not in href.lower():
            continue

        # Skip pagination and category links
        if any(skip in href.lower() for skip in ["page=", "category=", "#", "javascript"]):
            continue

        # Get title
        h3 = link.find("h3")
        title = h3.get_text(strip=True) if h3 else link.get_text(strip=True)

        if not title or len(title) < 10:
            continue

        # Skip navigation text
        if title.lower() in ["news", "read more", "view all", "all news"]:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Build full URL
        url = urljoin(base_url, href)

        # Try to find date
        date = None
        parent = link.find_parent(["div", "li", "article"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                d, m, y = match.groups()
                if len(y) == 2:
                    y = "20" + y
                date = f"{y}-{m.zfill(2)}-{d.zfill(2)}"

        # Get summary
        summary = None
        if parent:
            for p in parent.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 20 and text != title:
                    summary = text[:300]
                    break

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.80,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
