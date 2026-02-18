"""Site-specific extractors for finintinvestments.com.

Note: Finint Investments is an SGR (asset management company) that manages
various funds (Real Estate, Infrastructure, Private Capital, NPE, Public Markets).
They don't have a traditional portfolio company page - investments are made
through their managed funds.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.finintinvestments.com"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/management",
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract management team members from Finint Investments team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Team members are in div.ancestor-team-collapse > div.item-team
    for item in soup.select("div.ancestor-team-collapse div.item-team"):
        # Get name from strong tag in text paragraph
        text_div = item.select_one("div.text p")
        if not text_div:
            continue

        name_el = text_div.select_one("strong")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        if name in seen_names:
            continue
        seen_names.add(name)

        # Get title - it's the text after the strong tag
        # Get full text and remove name to get title
        full_text = text_div.get_text(separator=" ", strip=True)
        title = full_text.replace(name, "").strip()

        # Get photo URL
        photo_url = None
        photo_div = item.select_one("div.photo")
        if photo_div:
            # Try img src first
            img = photo_div.select_one("img")
            if img:
                src = img.get("src")
                if src:
                    photo_url = src

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "amministratore delegato" in title_lower or "ceo" in title_lower:
                role = "partner"
            elif "direttore generale" in title_lower:
                role = "partner"
            elif "vicedirettore" in title_lower:
                role = "partner"
            elif "consigliere delegato" in title_lower:
                role = "board"
            elif "direttore" in title_lower:
                role = "director"
            elif "responsabile" in title_lower or "head" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "analyst" in title_lower or "associate" in title_lower:
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news articles from Finint Investments news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_urls = set()

    # News items are in section.sn_news div.news_item
    for item in soup.select("section.sn_news div.news_item"):
        # Get title
        title_el = item.select_one("div.title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Get URL from the link
        url = None
        link = item.select_one("a.btn-arrow")
        if link:
            href = link.get("href", "")
            if href:
                url = urljoin(base_url, href)

        # Skip duplicates
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        # Get date
        date = None
        date_el = item.select_one("div.date")
        if date_el:
            date = date_el.get_text(strip=True)

        # Get summary/description
        summary = None
        desc_el = item.select_one("div.description")
        if desc_el:
            summary = desc_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.90,
        })

    return news


# Note: Finint Investments manages funds (RE, Infrastructure, Private Capital, NPE)
# rather than direct equity investments with portfolio companies.
# Individual fund investments are behind a disclaimer/login wall.
EXTRACTORS = {
    "team": extract_team,
    "news": extract_news,
}
