"""Site-specific extractors for anderapartners.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.anderapartners.com"



# URL paths — verified against url_status.json
URLS = {
    "portfolio": "/it/portfolio",
    "team": None,
    "news": "/en/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Andera Partners investment portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Each portfolio item is in a.investment-item
    for item in soup.select("a.investment-item"):
        # Get company name from h3.investment-title
        name_el = item.select_one("h3.investment-title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() == "confidential":
            continue

        # Get description
        description = None
        desc_el = item.select_one("p.investment-text")
        if desc_el:
            description = desc_el.get_text(strip=True)

        # Get sector from data-sector attribute (e.g., "therapeutic-products_62")
        sector = None
        data_sector = item.get("data-sector", "")
        if data_sector:
            # Clean up: remove trailing _XX number and convert dashes to spaces
            sector = data_sector.rsplit("_", 1)[0].replace("-", " ").title()

        # Get fund name from activity span
        fund = None
        activity_el = item.select_one("span.investment-activity")
        if activity_el:
            fund = activity_el.get_text(strip=True).lstrip("- ").strip()

        # Get investment date
        investment_date = None
        date_el = item.select_one("span.investment-date")
        if date_el:
            investment_date = date_el.get_text(strip=True)

        # Determine status from structural context:
        # 1. Primary: data-status attribute (structural, most reliable)
        # 2. Fallback: investment-state element content
        status = "current"
        data_status = item.get("data-status", "").lower().strip()

        # Check data-status attribute (preferred - structural)
        if data_status in ("sold", "exited", "exit", "divested"):
            status = "exited"
        elif data_status and data_status not in ("current", "active", "portfolio"):
            # Unknown data-status value - check if it indicates exit
            if data_status.startswith("sold") or data_status.startswith("exit"):
                status = "exited"

        # Fallback to investment-state element only if no data-status
        if not data_status:
            state_el = item.select_one("span.investment-state")
            if state_el:
                state_text = state_el.get_text(strip=True).lower()
                if state_text in ("sold", "exited", "exit", "divested"):
                    status = "exited"

        # Get company website from href
        website = None
        href = item.get("href", "")
        if href and href.startswith("http") and "anderapartners.com" not in href:
            website = href

        # Get logo URL
        logo_url = None
        img = item.select_one("img.investment-logo")
        if img:
            src = img.get("src")
            if src:
                logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": status,
            "fund": fund,
            "investment_date": investment_date,
            "logo_url": logo_url,
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Andera Partners team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Each team member is in a.team-item
    for item in soup.select("a.team-item"):
        # Get name from p.team-name
        name_el = item.select_one("p.team-name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Get title from p.team-function
        title = None
        title_el = item.select_one("p.team-function")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"
            elif "assistant" in title_lower or "office" in title_lower:
                role = "operations"

        # Get photo URL
        photo_url = None
        img = item.select_one("img.team-photo")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Get profile page URL
        linkedin = None
        profile_url = item.get("href")

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
    """Extract news/press releases from Andera Partners news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []

    # Each news item is in a.news-item
    for item in soup.select("a.news-item"):
        # Get title from h3.news-title
        title_el = item.select_one("h3.news-title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Get date from span.date
        date = None
        date_el = item.select_one("span.date")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get category from span.category
        category = None
        cat_el = item.select_one("span.category")
        if cat_el:
            category = cat_el.get_text(strip=True).lstrip("- ").strip()

        # Get type (Press releases, Publications, etc.)
        news_type = None
        type_el = item.select_one("span.type")
        if type_el:
            news_type = type_el.get_text(strip=True).lstrip("- ").strip()

        # Get article URL
        url = item.get("href", "")
        if url:
            url = urljoin(base_url, url)

        # Build summary from category and type
        summary = None
        if category or news_type:
            parts = [p for p in [category, news_type] if p]
            summary = " | ".join(parts)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.90,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
