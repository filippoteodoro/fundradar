"""Site-specific extractors for kyipcapital.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "kyipcapital.com"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/team/",
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from KYIP investments page.

    Structure:
    - Container: .pt-cv-content-item
    - Company name: img.pt-cv-thumbnail[alt]
    - Sector: .pt-cv-ctf-titolo-testo-home .pt-cv-ctf-value
    - Year: .pt-cv-ctf-anno-finanziamento .pt-cv-ctf-value
    - Link: a[href]
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for item in soup.select(".pt-cv-content-item"):
        # Get company name from img alt
        img = item.select_one("img.pt-cv-thumbnail")
        if not img:
            continue

        name = img.get("alt", "").strip()
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector
        sector = None
        sector_el = item.select_one(".pt-cv-ctf-titolo-testo-home .pt-cv-ctf-value")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get year
        year = None
        year_el = item.select_one(".pt-cv-ctf-anno-finanziamento .pt-cv-ctf-value")
        if year_el:
            year_text = year_el.get_text(strip=True)
            # Extract year number
            match = re.search(r"(\d{4})", year_text)
            if match:
                year = match.group(1)

        # Get link
        website = None
        link = item.find("a", href=True)
        if link:
            website = urljoin(base_url, link.get("href", ""))

        description = f"Investment year: {year}" if year else None

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from KYIP team page.

    Structure:
    - Container: .wpm_6310_team_member_info
    - Name: .wpm_6310_team_style_3_title
    - Title: .wpm_6310_team_style_3_designation
    - LinkedIn: ul.wpm_6310_team_style_3_social a[href*="linkedin"]
    - Photo: img.wpm-6310-main-image[src]
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".wpm_6310_team_member_info"):
        # Get name
        name_el = item.select_one(".wpm_6310_team_style_3_title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title
        title = None
        title_el = item.select_one(".wpm_6310_team_style_3_designation")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if "presidente" in title_lower or "ad " in title_lower or "ceo" in title_lower:
                role = "partner"
            elif "founding partner" in title_lower or "partner" in title_lower:
                role = "partner"
            elif "head" in title_lower or "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "analyst" in title_lower or "associate" in title_lower:
                role = "associate"

        # Get LinkedIn
        linkedin = None
        linkedin_el = item.select_one("a[href*='linkedin']")
        if linkedin_el:
            linkedin = linkedin_el.get("href", "")

        # Get photo
        photo_url = None
        img = item.select_one("img.wpm-6310-main-image")
        if img:
            src = img.get("src") or img.get("data-wpm-6310-image-attr")
            if src:
                photo_url = urljoin(base_url, src)

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
    Extract news from KYIP news page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find news articles
    for article in soup.select("article, .post, .news-item"):
        title_el = article.find(["h2", "h3", "h4"])
        if not title_el:
            continue

        link = title_el.find("a")
        if link:
            title = link.get_text(strip=True)
            url = urljoin(base_url, link.get("href", ""))
        else:
            title = title_el.get_text(strip=True)
            url = None

        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get date
        date = None
        time_el = article.find("time")
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
