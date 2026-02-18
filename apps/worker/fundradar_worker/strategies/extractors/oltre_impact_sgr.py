"""Site-specific extractors for oltreimpact.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DOMAIN = "www.oltreimpact.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/it/portafoglio-oltre-iii/",
    "team": "/it/team/",
    "news": "/it/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Oltre Impact portfolio page."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # Portfolio companies are in div.inner-wrap elements containing div.work-meta
    for wrap in soup.select("div.inner-wrap"):
        meta = wrap.select_one("div.work-meta")
        if not meta:
            continue

        # Get company name from h4.title
        name_el = meta.select_one("h4.title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Get sector/impact theme from h5
        sector = None
        sector_el = meta.select_one("h5")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Get detail URL from work-info link
        detail_url = None
        work_info = wrap.select_one("div.work-info a")
        if work_info:
            href = work_info.get("href")
            if href:
                detail_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
            "detail_url": detail_url,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Oltre Impact team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    # Team members have h3 names followed by h5 titles
    h3_elements = soup.select("h3.vc_custom_heading")

    for h3 in h3_elements:
        name = h3.get_text(strip=True)
        if not name or name.lower() in seen:
            continue

        # Skip non-name headings
        if len(name) > 50 or any(skip in name.lower() for skip in ["team", "oltre", "contact"]):
            continue

        seen.add(name.lower())

        # Get title from the next h5 sibling
        title = None
        next_sibling = h3.find_next_sibling("h5")
        if next_sibling:
            title = next_sibling.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "founder" in title_lower or "co-founder" in title_lower:
                role = "founder"
            elif "managing partner" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "cfo" in title_lower:
                role = "c-level"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "deputy" in title_lower:
                role = "deputy"
            elif "office" in title_lower:
                role = "admin"

        # Get LinkedIn from parent container
        linkedin = None
        parent = h3.parent
        if parent:
            linkedin_el = parent.select_one("a[href*='linkedin.com']")
            if linkedin_el:
                linkedin = linkedin_el.get("href")

        # Get photo from parent container
        photo_url = None
        if parent:
            parent_parent = parent.parent
            if parent_parent:
                img = parent_parent.select_one("img[data-nectar-img-src]")
                if img:
                    photo_url = img.get("data-nectar-img-src")

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/blog items from Oltre Impact news page.

    Structure: article.post
    - Title: h3.title a
    - URL: h3.title a[href]
    - Date: .grav-wrap .text span (Italian format: "28 Febbraio 2025")
    - Summary: div.excerpt p
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all article posts
    for article in soup.select("article.post"):
        # Get title from h3.title a
        title_el = article.select_one("h3.title a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL
        url = None
        href = title_el.get("href")
        if href:
            url = urljoin(base_url, href)

        # Get date from .grav-wrap .text span (Italian format)
        date = None
        grav_wrap = article.select_one(".grav-wrap .text span")
        if grav_wrap:
            date = grav_wrap.get_text(strip=True)

        # Get summary from div.excerpt p
        summary = None
        excerpt_p = article.select_one("div.excerpt p")
        if excerpt_p:
            summary = excerpt_p.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
