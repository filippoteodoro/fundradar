"""Site-specific extractors for farovalue.com (FARO Value).

Italian PE/VC firm focused on Real Economy,
Fashion/Luxury/Design, and Innovation strategies.

Note: Site has no public portfolio page showing investments.
Team members are on the about-us page using flip-box layout.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.faroalternativeinvestments.com"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": "/about-us/",
    "news": "/media-events/",
}
def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from FARO about-us page.

    Structure:
    - .flip-box-front-inner contains each team member
    - h5.flip-box-heading has the name
    - Text after h5 has the title
    - img.lazyload with data-orig-src has photo URL
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select(".flip-box-front-inner"):
        # Get name from h5 heading
        name_el = item.select_one("h5.flip-box-heading")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip non-person entries
        words = name.split()
        if len(words) < 2:
            continue

        # Dedupe
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from text after the h5
        title = None
        for sibling in name_el.next_siblings:
            if isinstance(sibling, str):
                text = sibling.strip()
                if text:
                    title = text
                    break

        # Get photo URL from lazy-loaded image
        photo_url = None
        img = item.select_one("img.lazyload")
        if img:
            src = img.get("data-orig-src") or img.get("src")
            if src and not src.startswith("data:"):
                photo_url = urljoin(base_url, src)

        # Infer role from title
        role = None
        if title:
            title_lower = title.lower()
            if "chairman" in title_lower or "ceo" in title_lower:
                role = "partner"
            elif "coo" in title_lower or "cfo" in title_lower:
                role = "partner"
            elif "fund manager" in title_lower:
                role = "principal"
            elif "director" in title_lower:
                role = "director"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from FARO website.

    Note: FARO does not have a public portfolio page showing investments.
    The /funds/ page only shows fund strategies, not portfolio companies.
    This function returns an empty list.
    """
    return []


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/media items from FARO Alternative Investments media page.

    Primary structure (current site):
    - Card container: .post-item
    - Title: .post-title a
    - URL: .post-title a[href]
    - Category: .cat-label (Media / Events / Press Releases)
    - Summary: .from_the_blog_excerpt

    Legacy fallback (older site theme):
    - article.fusion-post-large with blog-shortcode selectors.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Primary: Flatsome post cards
    for card in soup.select(".post-item"):
        title_el = card.select_one(".post-title a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        url = None
        href = title_el.get("href")
        if href:
            url = urljoin(base_url, href)

        category = None
        cat_el = card.select_one(".cat-label")
        if cat_el:
            category = cat_el.get_text(strip=True)

        summary = None
        summary_el = card.select_one(".from_the_blog_excerpt")
        if summary_el:
            summary = summary_el.get_text(" ", strip=True)
            if len(summary) > 300:
                summary = summary[:300]
        if category:
            summary = f"{category}: {summary}" if summary else category

        news.append({
            "title": title,
            "url": url,
            "date": None,
            "summary": summary,
            "confidence": 0.90,
        })

    # Fallback: older Avada list layout
    if news:
        return news
    for article in soup.select("article.fusion-post-large"):
        title_el = article.select_one("h1.blog-shortcode-post-title a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        url = None
        href = title_el.get("href")
        if href:
            url = urljoin(base_url, href)

        date = None
        meta_info = article.select_one(".fusion-meta-info")
        if meta_info:
            for span in meta_info.select("span"):
                if "vcard" in span.get("class", []) or "updated" in span.get("class", []):
                    continue
                text = span.get_text(strip=True)
                if any(
                    month in text
                    for month in [
                        "January", "February", "March", "April", "May", "June",
                        "July", "August", "September", "October", "November", "December",
                    ]
                ):
                    date = text
                    break

        summary = None
        content = article.select_one(".fusion-post-content-container p")
        if content:
            summary = content.get_text(strip=True)[:300]

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
