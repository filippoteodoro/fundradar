"""Site-specific extractors for sosteneo.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.sosteneo.com"



# URL paths — verified against live site
URLS = {
    "portfolio": "/projects",
    "team": None,
    "news": None,
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Sosteneo people page.

    Structure:
    - h4 for name
    - Position subheading
    - LinkedIn links
    - Images with team_member classes
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find h4 elements with names
    for h4 in soup.find_all(["h4", "h3"]):
        name = h4.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Check if it looks like a person name (contains at least 2 words)
        parts = name.split()
        if len(parts) < 2:
            continue

        # Skip non-name headings
        if any(skip in name.lower() for skip in [
            "team", "people", "about", "contact", "news", "projects",
            "partner", "infrastructure", "sosteneo"
        ]):
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find parent container
        parent = h4.find_parent(["div", "article", "section", "li"])

        # Look for title/position in sibling or nearby element
        title = None
        if parent:
            # Look for text elements after name
            for el in parent.find_all(["p", "span", "h5", "h6"]):
                text = el.get_text(strip=True)
                if text and text != name and len(text) < 100:
                    # Check if it looks like a title
                    if any(t in text.lower() for t in ["partner", "director", "manager", "analyst"]):
                        title = text
                        break

        # Also check next sibling
        if not title:
            next_el = h4.find_next_sibling(["p", "span", "div"])
            if next_el:
                text = next_el.get_text(strip=True)
                if text and len(text) < 100:
                    title = text

        # Extract LinkedIn
        linkedin = None
        if parent:
            for link in parent.find_all("a", href=True):
                href = link.get("href", "")
                if "linkedin.com" in href:
                    linkedin = href
                    break

        # Extract photo
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract infrastructure projects from Sosteneo projects page.

    Structure: article.node--type-projects with:
    - h3: project name
    - a[href*="/projects/"]: detail page link
    - img: project image
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for article in soup.select("article.node--type-projects"):
        # Get project name from h3
        name_el = article.select_one("h3")
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

        # Get detail page link
        website = None
        link = article.select_one('a[href*="/projects/"]')
        if link:
            href = link.get("href", "")
            if href:
                website = urljoin(base_url, href)

        # Get project image
        logo_url = None
        img = article.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src", "")
            if src:
                logo_url = urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": "Infrastructure",
            "website": website,
            "logo_url": logo_url,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Sosteneo news page.

    Structure:
    - News links: a[href*="/news/"]
    - Title: h3 within the link
    - Summary: p within the link
    - Date: extracted from img src path (YYYY-MM format)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all news article links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not href or "/news/" not in href:
            continue

        # Get title from h3
        h3 = link.find("h3")
        if not h3:
            continue

        title = h3.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Get full URL
        url = urljoin(base_url, href)

        # Get summary from p tag
        summary = None
        p = link.find("p")
        if p:
            summary_text = p.get_text(strip=True)
            # Skip the "Read more of..." pattern
            if not summary_text.startswith("Read more of"):
                summary = summary_text[:300]

        # Try to extract date from image path
        # Pattern: /public/YYYY-MM/image.jpg
        date = None
        img = link.find("img")
        if img:
            src = img.get("src", "")
            if src:
                # Look for YYYY-MM pattern in path
                date_match = re.search(r'/(\d{4})-(\d{2})/', src)
                if date_match:
                    year, month = date_match.groups()
                    date = f"{year}-{month}-01"

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
