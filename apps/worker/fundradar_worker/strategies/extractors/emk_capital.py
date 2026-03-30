"""Site-specific extractors for emkcapital.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "emkcapital.com"

# URL paths for monitoring
URLS = {
    "portfolio": "/our-portfolio",
    "team": "/our-people",
    "news": "/news",
}

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from EMK investments page.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Webflow collection list items
    for item in soup.select("div[role='listitem']"):
        # Company name
        name_el = item.select_one(".heading-medium, h3")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        # Skip team members if they appear in the same selector (unlikely but safe)
        if not name or len(name) < 2 or "Managing Partner" in name:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Description
        description = None
        desc_el = item.select_one("p.text-color-grey")
        if desc_el:
            description = desc_el.get_text(strip=True)

        # Link to detail page
        link_el = item.find("a", href=True)
        detail_url = urljoin(base_url, link_el.get("href", "")) if link_el else None

        companies.append({
            "name": name,
            "sector": None, # Usually in nested collection, hard to extract from raw HTML without JS
            "website": None, # On detail page
            "description": description,
            "status": "current",
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from EMK team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select("div[role='listitem']"):
        # Name
        name_el = item.select_one(".emk-key-contact-list_item-full-name, h2")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Title
        title = None
        title_el = item.select_one(".ps-key-contact-list_item-job-title")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role
        role = None
        if title:
            title_lower = title.lower()
            if "managing partner" in title_lower or "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "principal" in title_lower:
                role = "director"
            elif "associate" in title_lower:
                role = "associate"

        # LinkedIn - check if available in links
        linkedin = None
        linkedin_el = item.select_one("a[href*='linkedin.com']")
        if linkedin_el:
            linkedin = linkedin_el.get("href", "")

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from EMK news page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select(".ps-news-list_item, .emk-latest-news-list_item"):
        # Title
        title_el = item.select_one(".ps-news-list_item-title, .ps-latest-news-list_item-title, h3")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # URL
        link_el = item.find("a", href=True)
        url = urljoin(base_url, link_el.get("href", "")) if link_el else None

        # Date
        date = None
        date_el = item.select_one(".ps-news-list_item-published-date, .ps-latest-news-list_item-published-date")
        if date_el:
            date = date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "confidence": 0.85,
            "page_type": "news", # Triggers detail page fetch
        })

    return news


def extract_news_article(html: str, base_url: str) -> dict:
    """
    Extract full text from an EMK news article page.
    """
    soup = BeautifulSoup(html, "html.parser")
    content_el = soup.select_one(".ps-news-article-item_component, .section-news-article")
    if not content_el:
        return {}

    # Remove navigation/footer elements if any
    for junk in content_el.select(".ps-fixed-nav_component, footer"):
        junk.decompose()

    text = content_el.get_text(separator=" ", strip=True)
    return {
        "content": text,
        "confidence": 0.90
    }


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
    "news_article": extract_news_article,
}
