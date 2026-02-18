"""Site-specific extractors for perwyn.com (Perwyn Partners)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.perwyn.com"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/investments",
    "team": "/team",
    "news": "/news",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Perwyn investments page.

    Structure (verified Feb 2026 - Next.js SSR with Playwright):
    - Company links follow pattern /investments/{company-slug}
    - Each <a> card contains:
      - <span class="subtitle"> with sector label ("Consumer", "Technology", etc.)
      - <p> with company description
      - <div class="mt-3"> with stats (investment date, add-ons, etc.)
    - NO heading elements (h2-h5) inside cards
    - NO dedicated company name element
    - Company name must be derived from the URL slug
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_slugs = set()

    for link in soup.find_all("a", href=re.compile(r"/investments/[^?#]+$")):
        href = link.get("href", "")
        slug = href.rstrip("/").split("/")[-1]

        if not slug or slug == "investments":
            continue
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Skip filter/navigation items and non-company slugs
        if any(skip in slug for skip in [
            "view", "filter", "sector", "load",
            "abstract", "image-broken",
        ]):
            continue

        # Extract sector from subtitle element (must be done BEFORE name extraction)
        sector = None
        sector_el = link.find(class_=re.compile(r"subtitle|sector|category|tag"))
        if sector_el:
            sector_text = sector_el.get_text(strip=True)
            if sector_text and len(sector_text) < 40:
                sector = sector_text

        # Extract company name
        name = None

        # Try heading elements inside the link
        heading = link.find(["h2", "h3", "h4", "h5"])
        if heading:
            heading_text = heading.get_text(strip=True)
            # Reject sector labels that appear as headings
            if heading_text and len(heading_text) <= 60 and heading_text != sector:
                name = heading_text

        # Try class-based name element (exclude subtitle which contains sector)
        if not name:
            name_el = link.find(class_=re.compile(r"^(?!subtitle)\S*(?:name|company)\S*$"))
            if name_el:
                candidate = name_el.get_text(strip=True)
                if candidate and len(candidate) <= 60 and candidate != sector:
                    name = candidate

        # Derive name from slug (primary method for Perwyn's card structure)
        if not name:
            name = slug.replace("-", " ").title()
            name = re.sub(r"\bAnd\b", "&", name)

        if not name or len(name) < 2:
            continue

        companies.append({
            "name": name,
            "sector": sector,
            "website": urljoin(base_url, href),
            "description": None,
            "status": "current",
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Perwyn team page.
    
    Structure:
    - Team member links follow pattern /team/{person-slug}
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Strategy 1: Look for team member links
    for link in soup.find_all("a", href=re.compile(r"^/team/[^?#]+$")):
        href = link.get("href", "")
        slug = href.rstrip("/").split("/")[-1]
        
        if not slug or slug == "team":
            continue
        
        # Get name from link text or convert slug
        name = link.get_text(strip=True)
        if not name or len(name) < 3:
            name = slug.replace("-", " ").title()
        
        # Validate as a person name (at least 2 words)
        words = name.split()
        if len(words) < 2:
            continue
            
        if name.lower() in seen_names:
            continue
            
        seen_names.add(name.lower())
        
        # Try to get title from parent container
        title = None
        parent = link.find_parent(["div", "article", "li"])
        if parent:
            title_el = parent.find(class_=re.compile(r"title|role|position"))
            if title_el and title_el != link:
                title = title_el.get_text(strip=True)
        
        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "principal" in title_lower:
                role = "principal"
            elif "cfo" in title_lower or "coo" in title_lower:
                role = "c-level"
            elif "associate" in title_lower:
                role = "associate"
        
        # Get photo if available
        photo_url = None
        if parent:
            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    photo_url = urljoin(base_url, src)
        
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
    """
    Extract news from Perwyn news page.
    
    Structure:
    - News links follow pattern /news/{article-slug}
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Date pattern: "DD Mon YYYY" (e.g. "15 Jan 2025", "3 Dec 2024")
    date_re = re.compile(
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})",
        re.IGNORECASE,
    )

    # Strategy 1: Look for news links
    for link in soup.find_all("a", href=re.compile(r"^/news/[^?#]+$")):
        href = link.get("href", "")

        # Get full text including date (use separator to prevent merging)
        full_text = link.get_text(separator=" ", strip=True)

        # Try to extract date from the link text
        date = None
        date_match = date_re.search(full_text)
        if date_match:
            # Extract the date portion and pass raw to normalize_news_date later
            date = date_match.group(0)

        # Get title: full text minus the date portion
        title = full_text
        if date_match:
            title = full_text[:date_match.start()].strip()
            if not title:
                title = full_text[date_match.end():].strip()

        if not title or len(title) < 15:
            # Try to get from slug
            slug = href.rstrip("/").split("/")[-1]
            if slug and slug != "news":
                title = slug.replace("-", " ").title()

        if not title or title.lower() in seen_titles:
            continue

        # Skip navigation
        if any(skip in title.lower() for skip in ["view all", "see more", "older", "newer", "page"]):
            continue

        seen_titles.add(title.lower())

        # If no date found in link text, try parent container
        if not date:
            parent = link.find_parent(["div", "article", "li"])
            if parent:
                date_el = parent.select_one("time, .date, [datetime]")
                if date_el:
                    date = date_el.get("datetime") or date_el.get_text(strip=True)

        news.append({
            "title": title,
            "url": urljoin(base_url, href),
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
