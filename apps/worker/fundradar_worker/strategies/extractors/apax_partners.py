"""Site-specific extractors for apax.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.apax.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/partnerships/",
    "team": "/people/our-team/",
    "news": "/news-views/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Apax Partners partnerships page.

    Structure: Links to /partnerships/[company-slug]/ with company names as link text.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all links to partnership pages
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        # Only process partnership links (not filter links)
        if "/partnerships/" not in href:
            continue
        if href == "/partnerships/" or href.endswith("/partnerships/"):
            continue
        if "?" in href:  # Skip filter/query links
            continue

        # Extract company name from link text
        name = link.get_text(strip=True)

        # If no text, try to get from img alt
        if not name:
            img = link.find("img")
            if img:
                name = img.get("alt", "").strip()

        if not name or len(name) < 2:
            continue

        # Skip navigation items
        name_lower = name.lower()
        if any(skip in name_lower for skip in ["menu", "back", "view all", "filter", "sector", "strategy"]):
            continue

        # Skip duplicates
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Build company URL
        website = urljoin(base_url, href)

        # Determine status from structural context (URL path or parent section class/id)
        # Avoid keyword matching on general parent text
        status = "current"
        # Check URL path for status indicators
        if any(segment in href.lower() for segment in ["/realised/", "/exited/", "/former/"]):
            status = "exited"
        else:
            # Check parent section for structural status indicators
            parent = link.find_parent(["div", "section", "li"], class_=re.compile(r"realised|exited|former|historical", re.I))
            if parent:
                status = "exited"
            else:
                # Check parent section id for status
                parent_with_id = link.find_parent(id=re.compile(r"realised|exited|former|historical", re.I))
                if parent_with_id:
                    status = "exited"

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": None,
            "status": status,
            "confidence": 0.80,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Apax Partners people page.

    Structure: Links to /people/our-team/[member-name]/ with images.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Find all links to team member pages
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        # Only process team member links
        if "/people/our-team/" not in href:
            continue
        if href == "/people/our-team/" or href.endswith("/our-team/"):
            continue

        # Extract name from link URL (slug to name)
        slug = href.rstrip("/").split("/")[-1]
        name = slug.replace("-", " ").title()

        # Also try to get name from link text or img alt
        link_text = link.get_text(strip=True)
        if link_text and len(link_text) > 2:
            name = link_text

        img = link.find("img")
        if img:
            alt = img.get("alt", "").strip()
            if alt and alt.lower() != "image" and len(alt) > 2:
                name = alt

        if not name or len(name) < 3:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get photo URL
        photo_url = None
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Title would need to be fetched from detail page
        # For now, we don't have it
        members.append({
            "name": name,
            "title": None,
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.75,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Apax Partners news & views page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Date pattern
    date_pattern = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)

    # Find all news links
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        # Look for news article links
        if not any(segment in href.lower() for segment in ["/news", "/insights", "/press", "/article"]):
            continue

        # Get title — check h2, h3, h4 (Apax uses h4 for article titles)
        title = None
        for htag in ["h2", "h3", "h4"]:
            heading = link.find(htag)
            if heading:
                title = heading.get_text(separator=" ", strip=True)
                break

        if not title:
            # Fallback to link text, but skip if it looks like a category label
            raw = link.get_text(separator=" ", strip=True)
            # Only use link text if it looks like a real title (>30 chars, not a label)
            if raw and len(raw) > 30:
                title = raw

        if title:
            # Strip trailing read-time metadata (e.g. "4 min read", "3 minute read")
            title = re.sub(r"\s*\d+\s*min(?:ute)?s?\s*read\s*$", "", title, flags=re.I).strip()
            # Strip trailing date metadata that got merged into title
            title = re.sub(r"\s*\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*$", "", title, flags=re.I).strip()
            # Strip category prefixes that get concatenated into title
            title = re.sub(r"^(Press Release|Insight|News|Article|Report|Case Study)\s*[-–—:]\s*", "", title, flags=re.I).strip()
            title = re.sub(r"^(Press Release|Insight|News|Article|Report|Case Study)\s+", "", title, flags=re.I).strip()
            # If title still ends with "..." (server-side truncation), try to reconstruct from URL slug
            if title.endswith("...") and href:
                slug = href.rstrip("/").split("/")[-1]
                if slug and len(slug) > 10:
                    reconstructed = slug.replace("-", " ").strip()
                    # Only use slug if it's longer than the truncated title
                    if len(reconstructed) > len(title):
                        title = reconstructed[0].upper() + reconstructed[1:]
                        # Fix known proper nouns and acronyms
                        title = re.sub(r'\bapax\b', 'Apax', title, flags=re.IGNORECASE)
                        title = re.sub(r'\bai\b', 'AI', title)

        if not title or len(title) < 10:
            continue

        # Skip navigation
        if title.lower() in ["news", "read more", "view all", "news & views"]:
            continue

        # Skip duplicates
        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Build URL
        url = urljoin(base_url, href)

        # Try to find date
        date = None
        parent = link.find_parent(["div", "li", "article"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                day, month, year = match.groups()
                months = {
                    "january": "01", "february": "02", "march": "03", "april": "04",
                    "may": "05", "june": "06", "july": "07", "august": "08",
                    "september": "09", "october": "10", "november": "11", "december": "12"
                }
                month_num = months.get(month.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"

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
