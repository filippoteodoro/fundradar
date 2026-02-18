"""Site-specific extractors for abenex.com."""
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.abenex.com"



# URL paths for monitoring
# News uses WP REST API — returns JSON with structured dates, titles, excerpts.
URLS = {
    "portfolio": "/portfolios/",
    "team": "/team/",
    "news": "/wp-json/wp/v2/posts?per_page=20&_fields=id,title,date,link,excerpt",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Abenex portfolio page.

    Structure:
    - Container: li.filtr-item
    - Name: .comp-item_infos__title
    - Theme: .comp-item_infos__sub-terms (investment theme)
    - Status: data-statut attribute (in-portafoglio = current, cedute = exited)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for item in soup.select("li.filtr-item"):
        # Get company name
        name_el = item.select_one(".comp-item_infos__title")
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

        # Skip real estate property/fund names
        if re.match(r"^portefeuille\s", name_lower):
            continue

        # Get status from data attribute
        data_statut = item.get("data-statut", "")
        if data_statut == "cedute":
            status = "exited"
        else:
            status = "current"

        # Get sector/theme from sub-terms
        sector = None
        sub_terms = item.select(".comp-item_infos__sub-terms")
        if sub_terms:
            # First sub-terms is usually investment theme
            sector = sub_terms[0].get_text(strip=True)

        # Get strategy (Mid Cap / Small Cap for PE; Core+/Value Add for real estate)
        strategy = item.get("data-strategy", "")

        # Skip real estate entries (Core+, Value Add strategies)
        strategy_lower = strategy.lower()
        if any(re in strategy_lower for re in ["core", "value-add", "value_add", "immobilier", "real-estate", "actif"]):
            continue

        description = None
        if strategy:
            strategy_text = strategy.replace("-it", "").replace("-", " ").title()
            description = f"Strategy: {strategy_text}"

        # Get link to company page
        website = None
        link_el = item.select_one("a[href]")
        if link_el:
            href = link_el.get("href", "")
            if href and "/company/" in href:
                website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": status,
            "confidence": 0.90,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Abenex team page.

    Structure:
    - Container: li.filtr-item or wrapper with team member data
    - Name: h3.team-item_content__title or .comp-item_infos__title
    - Title: p.team-item_content__infos or .comp-item_infos__sub-terms
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for item in soup.select("li.filtr-item"):
        # Try to get name from h3 first, then from div
        name_el = item.select_one("h3.team-item_content__title")
        if not name_el:
            name_el = item.select_one(".comp-item_infos__title")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get title from p or sub-terms
        title = None
        title_el = item.select_one("p.team-item_content__infos")
        if not title_el:
            title_el = item.select_one(".comp-item_infos__sub-terms")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "founder" in title_lower or "chairman" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "cfo" in title_lower or "chief" in title_lower:
                role = "director"
            elif "analyst" in title_lower or "associate" in title_lower:
                role = "associate"

        # Get link to profile
        profile_url = None
        link_el = item.select_one("a[href]")
        if link_el:
            href = link_el.get("href", "")
            if href and "/team/" in href:
                profile_url = urljoin(base_url, href)

        # Get photo URL from background-image style
        photo_url = None
        img_div = item.select_one(".team-item_image[style]")
        if img_div:
            style = img_div.get("style", "")
            if "url(" in style:
                start = style.find("url(") + 4
                end = style.find(")", start)
                if end > start:
                    photo_url = style[start:end].strip("\"'")

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


def _strip_html(text: str) -> str:
    """Strip HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Abenex.

    Primary: Parse WP REST API JSON response (structured dates + titles).
    Fallback: Parse HTML listing page (no dates available).
    """
    news = []
    seen_titles = set()

    # Try parsing as WP REST API JSON response
    try:
        posts = json.loads(html)
        if isinstance(posts, list) and posts and isinstance(posts[0], dict):
            for post in posts:
                # Title is returned as {"rendered": "..."} by WP API
                title_obj = post.get("title", {})
                title = title_obj.get("rendered", "") if isinstance(title_obj, dict) else str(title_obj)
                title = _strip_html(title)
                if not title or len(title) < 10:
                    continue

                title_lower = title.lower()
                if title_lower in seen_titles:
                    continue
                seen_titles.add(title_lower)

                # WP API date format: "2026-02-06T10:04:59"
                date = post.get("date")

                # URL
                url = post.get("link")

                # Excerpt is returned as {"rendered": "..."} with HTML
                summary = None
                excerpt_obj = post.get("excerpt", {})
                excerpt = excerpt_obj.get("rendered", "") if isinstance(excerpt_obj, dict) else ""
                if excerpt:
                    summary = _strip_html(excerpt)[:300]

                news.append({
                    "title": title,
                    "url": url,
                    "date": date,
                    "summary": summary,
                    "confidence": 0.90,
                })
            return news
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    # Fallback: HTML parsing (for backwards compatibility)
    soup = BeautifulSoup(html, "html.parser")

    for article in soup.select("article.elementor-post"):
        title_el = article.select_one("h3.elementor-post__title a")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = title_el.get("href")
        if url:
            url = urljoin(base_url, url)

        summary = None
        excerpt_el = article.select_one(".elementor-post__excerpt p")
        if excerpt_el:
            summary = excerpt_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": None,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
