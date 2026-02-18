"""Site-specific extractors for liftt.com.

LIFTT uses Avada/Fusion Builder with portfolio and team components.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.liftt.com"


# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/investire-it/",
    "team": "/chi-siamo-it/",
    "news": "/news-it/",
}
# Known category classes used by LIFTT
CATEGORY_CLASSES = {
    "healthcare": "Healthcare",
    "biotech": "Biotech",
    "iot": "IoT",
    "enviroment": "Environment",  # Note: their typo
    "new-materials": "New Materials",
    "photonics": "Photonics",
    "mobility": "Mobility",
    "education": "Education",
    "retail": "Retail",
    "semiconductors": "Semiconductors",
    "energy": "Energy",
    "foodtech": "FoodTech",
    "spacetech": "SpaceTech",
    "smart-city": "Smart City",
    "robotics": "Robotics",
    "ai": "AI",
    "fintech": "FinTech",
    "medtech": "MedTech",
    "cleantech": "CleanTech",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Fusion layout columns with portfolio links."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # LIFTT uses fusion-layout-column items containing portfolio-item links
    items = soup.select("li.fusion-layout-column")

    for item in items:
        # Must have a portfolio-item link
        link = item.select_one('a[href*="portfolio-item"]')
        if not link:
            continue

        href = link.get("href", "")

        # Extract company name from URL slug
        match = re.search(r"/portfolio-item/([^/]+)/?", href)
        if not match:
            continue

        slug = match.group(1)
        # Clean up slug: remove trailing numbers, replace hyphens with spaces
        name = re.sub(r"-\d+$", "", slug)  # remove -2 at end
        name = name.replace("-", " ").title()

        if not name or len(name) < 2:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Extract sector from category link text (more accurate than class)
        sector = None
        cat_link = item.select_one('a[href*="categoria_portfolio"]')
        if cat_link:
            sector = cat_link.get_text(strip=True)

        # Fallback to item classes if no category link
        if not sector:
            item_classes = " ".join(item.get("class", []))
            for cat_class, cat_name in CATEGORY_CLASSES.items():
                if cat_class in item_classes.lower():
                    sector = cat_name
                    break

        # Extract logo/image URL from background image in style or data attribute
        logo_url = None
        wrapper = item.select_one('[data-bg-url]')
        if wrapper:
            logo_url = wrapper.get("data-bg-url")

        # Fallback: extract from inline style
        if not logo_url:
            style = item.get("style", "")
            bg_match = re.search(r'url\(([^)]+)\)', style)
            if bg_match:
                logo_url = bg_match.group(1)

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,  # External website not available on listing page
            "description": None,
            "logo_url": logo_url,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Fusion buttons with role in h6 headings."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # LIFTT uses fusion-button elements for names with role in h6.fusion-title-heading
    name_pattern = re.compile(r"^[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?$")
    buttons = soup.select("a.fusion-button")

    for btn in buttons:
        name = btn.get_text(strip=True)

        # Must match person name pattern
        if not name_pattern.match(name):
            continue

        if len(name) < 5:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find the 1/4 column containing this button (the person card)
        col = btn.find_parent("div", class_=lambda x: x and "fusion_builder_column_1_4" in x)

        title = None
        linkedin = None
        photo_url = None

        if col:
            # Look for role in h6.fusion-title-heading
            h6 = col.select_one("h6.fusion-title-heading")
            if h6:
                title = h6.get_text(strip=True)

            # Also try p element as fallback
            if not title:
                p = col.select_one("p")
                if p:
                    title = p.get_text(strip=True)

            # Look for LinkedIn link
            for link in col.select('a[href*="linkedin"]'):
                linkedin = link.get("href")
                break

            # Look for profile image in the column
            img = col.select_one("img")
            if img:
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if src:
                    photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from blog/news section."""
    soup = BeautifulSoup(html, "html.parser")
    news = []

    # Common news/blog item selectors
    selectors = [
        ".fusion-blog-post",
        "article.post",
        ".fusion-post-card",
        ".news-item",
    ]

    items = []
    for selector in selectors:
        items = soup.select(selector)
        if items:
            break

    for item in items:
        # Get title
        title = None
        title_el = item.select_one(".entry-title a, .fusion-post-title a, h2 a, h3 a")
        if title_el:
            title = title_el.get_text(strip=True)

        if not title or len(title) < 5:
            continue

        # Get URL
        url = None
        link = item.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        # Get date
        date = None
        date_el = item.select_one("time, .date, .entry-date, .fusion-date")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        # Get summary
        summary = None
        summary_el = item.select_one(".entry-content p, .fusion-post-content-container p, .excerpt")
        if summary_el:
            summary = summary_el.get_text(strip=True)[:300]

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
