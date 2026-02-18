"""Site-specific extractors for keycapital.it.

Key Capital is a Venture Incubator focused on early-stage digital startups.
The main website is a single-page app with portfolio carousel and team info.
News is on a separate WordPress blog at /news/
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.keycapital.it"



# URL paths for monitoring - verified against live site
# Key Capital is a single-page app - portfolio and team are on homepage
URLS = {
    "portfolio": "/",  # Homepage carousel
    "team": "/",       # Homepage team section
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Key Capital homepage carousel."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio logos are in the owl-carousel div
    carousel = soup.select_one("#owl-portfolio")
    if not carousel:
        return companies

    for item in carousel.select("div"):
        link = item.select_one("a")
        if not link:
            continue

        # Get company website
        href = link.get("href", "")
        if not href or href == "#":
            continue

        # Get company name from image filename or alt
        img = link.select_one("img.img-portfolio")
        if not img:
            continue

        # Try alt text first
        name = img.get("alt", "")

        # Fallback: extract from image src filename
        if not name:
            src = img.get("src", "")
            if src:
                # Extract filename without path and extension
                filename = src.split("/")[-1].split(".")[0]
                name = filename.replace("-", " ").replace("_", " ").title()

        if not name or len(name) < 2:
            continue

        # Normalize name
        name = name.strip()

        # Skip duplicates
        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        companies.append({
            "name": name,
            "sector": "Technology",  # Key Capital focuses on digital startups
            "website": href if href.startswith("http") else None,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Key Capital homepage."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Team section with .user divs
    team_section = soup.select_one("#team")
    if not team_section:
        return members

    for user in team_section.select(".user"):
        # Get name
        name_el = user.select_one("span.nome")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        if name in seen_names:
            continue
        seen_names.add(name)

        # Get title
        title = None
        title_el = user.select_one("span.titolo")
        if title_el:
            title = title_el.get_text(strip=True)

        # Get photo URL
        photo_url = None
        img = user.select_one("img.photo")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "ceo" in title_lower or "founder" in title_lower:
                role = "partner"
            elif "general manager" in title_lower:
                role = "partner"
            elif "cda" in title_lower:  # Board member
                role = "board"
            elif "director" in title_lower or "lead" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"

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
    """Extract news articles from Key Capital WordPress blog."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_urls = set()

    # WordPress article posts
    for article in soup.select("article.post"):
        # Get title and URL
        title_link = article.select_one("h2.entry-title a")
        if not title_link:
            continue

        title = title_link.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        url = title_link.get("href", "")
        if url:
            url = urljoin(base_url, url)

        # Skip duplicates
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        # Get date from time element
        date = None
        time_el = article.select_one("time.entry-date.published")
        if time_el:
            date = time_el.get_text(strip=True)

        # Get summary from entry content
        summary = None
        content_el = article.select_one("div.entry-content")
        if content_el:
            # Get first paragraph
            first_p = content_el.find("p")
            if first_p:
                summary = first_p.get_text(strip=True)[:300]

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
