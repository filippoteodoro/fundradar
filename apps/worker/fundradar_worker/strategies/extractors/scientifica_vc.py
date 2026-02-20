"""Site-specific extractors for scientifica.vc.

Scientifica VC is an Italian deep-tech venture fund.
Modern website with team at /team/ and portfolio at /portfolio-startup/.
"""
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DOMAIN = "scientifica.vc"



# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio-startup/",
    "team": "/team/?fr_src=fundradar",
    "news": "/media-ed-eventi/?fr_src=fundradar",
}


def _clean_text(value: str | None) -> str | None:
    """Collapse whitespace and return None for empty values."""
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def _normalize_date(value: str | None) -> str | None:
    """Normalize common date formats to YYYY-MM-DD when possible."""
    if not value:
        return None
    text = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if m:
        d, month, y = m.groups()
        return f"{y}-{month.zfill(2)}-{d.zfill(2)}"
    return text


def _extract_news_from_wp_api(base_url: str) -> list[dict]:
    """Fallback extraction from WordPress REST API."""
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    root = f"{parsed.scheme}://{parsed.netloc}"
    endpoint = (
        f"{root}/wp-json/wp/v2/posts"
        "?per_page=30&_fields=date,link,title,excerpt"
    )

    try:
        response = requests.get(
            endpoint,
            timeout=20,
            headers={
                "User-Agent": "Fundradar/1.0 (https://fundradar.io; research purposes)",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        if response.status_code != 200:
            return []
        payload = response.json()
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    news = []
    seen_titles: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue

        title_html = (item.get("title") or {}).get("rendered") if isinstance(item.get("title"), dict) else None
        title = _clean_text(BeautifulSoup(title_html or "", "html.parser").get_text(" ", strip=True))
        if not title or len(title) < 8:
            continue

        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)

        excerpt_html = (item.get("excerpt") or {}).get("rendered") if isinstance(item.get("excerpt"), dict) else None
        summary = _clean_text(BeautifulSoup(excerpt_html or "", "html.parser").get_text(" ", strip=True))

        news.append({
            "title": title,
            "url": item.get("link"),
            "date": _normalize_date(item.get("date")),
            "summary": summary[:350] if summary else None,
            "confidence": 0.90,
        })

        if len(news) >= 40:
            break

    return news


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Scientifica team page.

    Structure:
    - .internal-team-card contains each member
    - h3 has the name
    - p has the title (sibling or child)
    - a[href*="linkedin"] has LinkedIn link
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for card in soup.select(".internal-team-card"):
        # Get name from h3
        h3 = card.select_one("h3")
        if not h3:
            continue

        name = h3.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-names
        words = name.split()
        if len(words) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from p tag
        title = None
        p = card.select_one("p")
        if p:
            title = p.get_text(strip=True)
            # Clean up title - remove @ references
            if "@" in title:
                title = title.split("@")[0].strip()

        # Get LinkedIn
        linkedin = None
        linkedin_el = card.select_one("a[href*='linkedin']")
        if linkedin_el:
            linkedin = linkedin_el.get("href")

        # Get photo
        photo_url = None
        img = card.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                photo_url = urljoin(base_url, src)

        # Infer role from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "head" in title_lower or "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower:
                role = "associate"
            elif "analyst" in title_lower:
                role = "analyst"

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
    """Extract news/media posts from Scientifica media page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles: set[str] = set()

    # Flexible card selectors to tolerate CMS/theme updates.
    cards = soup.select(
        "article, .post, .news-item, .media-item, .w-grid-item, .t-entry"
    )

    for card in cards:
        title_el = card.select_one(
            "h2, h3, .entry-title, .post-title, .mcb-item-title-inner, a[title]"
        )
        if not title_el:
            continue

        title = _clean_text(title_el.get_text(" ", strip=True))
        if not title or len(title) < 8:
            continue

        key = title.lower()
        if key in seen_titles:
            continue

        link_el = None
        if title_el.name == "a":
            link_el = title_el
        else:
            link_el = title_el.find_parent("a") or card.select_one("a[href]")

        url = None
        if link_el:
            href = (link_el.get("href") or "").strip()
            if href and not href.startswith("#"):
                url = urljoin(base_url, href)

        date = None
        time_el = card.select_one("time")
        if time_el:
            date = time_el.get("datetime") or time_el.get_text(" ", strip=True)
        if not date:
            date_el = card.select_one(".date, .post-date, .entry-date, .meta-date")
            if date_el:
                date = date_el.get_text(" ", strip=True)

        summary = None
        summary_el = card.select_one("p, .excerpt, .entry-summary, .post-excerpt")
        if summary_el:
            summary = _clean_text(summary_el.get_text(" ", strip=True))

        seen_titles.add(key)
        news.append({
            "title": title,
            "url": url,
            "date": _normalize_date(date),
            "summary": summary[:350] if summary else None,
            "confidence": 0.86,
        })

        if len(news) >= 40:
            break

    if news:
        return news

    # If the media page shell is JS-heavy, fallback to WP posts API.
    return _extract_news_from_wp_api(base_url)


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Scientifica portfolio page.

    Structure:
    - h3.t-entry-title contains company name
    - Parent a tag has link to detail page
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for h3 in soup.select("h3.t-entry-title"):
        name = h3.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get link to detail page
        parent_link = h3.find_parent("a")
        website = None
        if parent_link:
            href = parent_link.get("href")
            if href:
                website = urljoin(base_url, href)

        # Get logo
        logo_url = None
        if parent_link:
            img = parent_link.select_one("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src and not src.startswith("data:"):
                    logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": None,  # Sector not easily extractable from list view
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "logo_url": logo_url,
            "confidence": 0.90,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
