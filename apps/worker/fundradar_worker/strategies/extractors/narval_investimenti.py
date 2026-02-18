"""Site-specific extractors for www.narvalinvestimenti.it."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.narvalinvestimenti.it"



# URL paths for monitoring - verified against live site
# Narval has multiple portfolio sections by sector
URLS = {
    "portfolio": "/partecipazioni-industriali/",
    "team": "/il-gruppo/",
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Narval Investimenti.

    Companies are displayed with h4 titles in list items.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Companies are in h4 elements
    h4s = soup.select("h4")

    for h4 in h4s:
        name = h4.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get description from following content
        description = None
        parent = h4.find_parent("li")
        if parent:
            # Find all p elements in the same container
            ps = parent.select("p")
            for p in ps:
                text = p.get_text(strip=True)
                if text and len(text) > 20 and "anno di ingresso" not in text.lower():
                    description = text[:500]
                    break

        # Get website if available
        website = None
        if parent:
            site_link = parent.select_one('a[href*="visita"], a[href*="http"]')
            if site_link:
                href = site_link.get("href", "")
                if href and "narvalinvestimenti" not in href:
                    website = href

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
    Extract team members from Narval Investimenti /il-gruppo/ page.

    Members are in .accordion_content with p elements containing
    two span elements (name and title).
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Pattern: Accordion content with p > span pairs
    for accordion in soup.select(".accordion_content"):
        for p in accordion.select("p"):
            spans = p.select("span")
            if len(spans) >= 2:
                name = spans[0].get_text(strip=True)
                title = spans[1].get_text(strip=True)

                if not name or len(name) < 3 or name.lower() in seen_names:
                    continue

                # Skip company names (contain S.P.A., S.r.l., etc.)
                if re.search(r'\b(S\.?P\.?A\.?|S\.?r\.?l\.?|S\.?a\.?s\.?|LLC|Ltd)\b', name, re.IGNORECASE):
                    continue

                seen_names.add(name.lower())

                # Determine role from title
                role = None
                if title:
                    title_lower = title.lower()
                    if "presidente" in title_lower:
                        role = "partner"
                    elif "consigliere" in title_lower:
                        role = "director"
                    elif "sindaco" in title_lower:
                        role = "board"
                    elif "responsabile" in title_lower:
                        role = "director"

                members.append({
                    "name": name,
                    "title": title,
                    "role": role,
                    "linkedin": None,
                    "email": None,
                    "photo_url": None,
                    "confidence": 0.90,
                })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/comunicati from Narval Investimenti."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for article in soup.select("article, .post, .news-item, .comunicato"):
        title_el = article.select_one("h2 a, h3 a, h4 a, .title a")
        if not title_el:
            title_el = article.select_one("h2, h3, h4, .title")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        url = None
        if title_el.name == "a":
            url = title_el.get("href")
        else:
            link = article.select_one("a[href]")
            if link:
                url = link.get("href")
        if url:
            url = urljoin(base_url, url)

        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
