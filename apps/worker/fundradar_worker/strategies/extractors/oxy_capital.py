"""Site-specific extractors for oxycapital.com."""
import re
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

DOMAIN = "oxycapital.com"

# News fetched from WordPress REST API (/wp-json/wp/v2/posts) — not from HTML.
ALWAYS_EXTRACT = True

# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": "https://oxycapital.com/private-equity-and-mezzanine-debt/",
    "team": None,
    # Monitor the WP API endpoint directly to avoid blocked HTML/news paths.
    "news": "https://oxycapital.com/wp-json/wp/v2/posts?per_page=20&_fields=id,title,date,link,excerpt",
}


def _parse_wp_posts_json(raw: str) -> list[dict]:
    """Parse WordPress posts payload from monitor response body."""
    if not raw or not raw.strip():
        return []

    try:
        posts = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(posts, list):
        return []

    from html import unescape

    news = []
    seen_urls = set()
    for post in posts:
        if not isinstance(post, dict):
            continue

        title_obj = post.get("title", {})
        title = title_obj.get("rendered", "") if isinstance(title_obj, dict) else str(title_obj)
        title = re.sub(r"<[^>]+>", "", unescape(title)).strip()
        if not title or len(title) < 10:
            continue

        url = post.get("link", "")
        if not isinstance(url, str) or not url or url in seen_urls:
            continue
        seen_urls.add(url)

        date = None
        date_str = post.get("date", "")
        if isinstance(date_str, str) and date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date = dt.strftime("%Y-%m-%d")
            except Exception:
                date = None

        summary = None
        excerpt_obj = post.get("excerpt", {})
        excerpt = excerpt_obj.get("rendered", "") if isinstance(excerpt_obj, dict) else ""
        if excerpt:
            summary = re.sub(r"<[^>]+>", "", unescape(excerpt)).strip()
            if len(summary) > 200:
                summary = summary[:200] + "..."

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.90,
        })

    return news


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Oxy Capital portfolio pages.

    Note: Oxy Capital has multiple portfolio pages by strategy.
    This extractor works on any of them.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_urls = set()

    # Portfolio items are in li.eg-portfolio-wrapper or li.eg-portfolio_nolink-wrapper
    for item in soup.select("li.eg-portfolio-wrapper, li.eg-portfolio_nolink-wrapper"):
        # Get company logo/image
        img = item.select_one("div.esg-entry-media img")
        if not img:
            continue

        # Try to get company name from image alt or filename
        name = None
        alt = img.get("alt", "")
        if alt and len(alt) > 2:
            name = alt

        # Fallback: extract from image filename
        if not name:
            src = img.get("src", "")
            if src:
                # Extract filename without extension
                filename = src.split("/")[-1].split(".")[0]
                # Clean up common patterns
                name = filename.replace("-", " ").replace("_", " ")
                name = re.sub(r'\b(OK|ok|logo|Logo|LOGO)\b', '', name).strip()
                name = re.sub(r'e\d+$', '', name).strip()  # Remove e1234567 suffixes
                name = name.title()

        if not name or len(name) < 2:
            continue

        # Get website from link
        website = None
        link = item.select_one("a.eg-invisiblebutton")
        if link:
            href = link.get("href", "")
            if href and "oxycapital" not in href:
                website = href

        # Skip duplicates by URL
        url_key = website or name.lower()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.80,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Oxy Capital team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []

    # Team members are in li.eg-oxy-wrapper
    for item in soup.select("li.eg-oxy-wrapper"):
        # Get name from div.eg-oxy-element-3 or div.esg-content
        name_el = item.select_one("div.eg-oxy-element-3")
        if not name_el:
            name_el = item.select_one("div.esg-content")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        # Get title and email from div.eg-oxy-element-11
        title = None
        email = None
        info_el = item.select_one("div.eg-oxy-element-11")
        if info_el:
            info_text = info_el.get_text(separator=" ", strip=True)
            # Format is usually "Title | Location \n email@domain.com"
            parts = info_text.split()

            # Extract email
            for part in parts:
                if "@" in part and "oxycapital" in part:
                    email = part.replace("\u200b", "")  # Remove zero-width spaces
                    break

            # Extract title (everything before the email/location part)
            if "|" in info_text:
                title = info_text.split("|")[0].strip()
            elif "@" in info_text:
                title = info_text.split("@")[0].rsplit(" ", 1)[0].strip()

        # Get photo URL
        photo_url = None
        img = item.select_one("div.esg-entry-media img")
        if img:
            src = img.get("src")
            if src:
                photo_url = urljoin(base_url, src)

        # Determine role category from title
        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "founder" in title_lower:
                role = "partner"
            elif "director" in title_lower or "head" in title_lower:
                role = "director"
            elif "manager" in title_lower or "principal" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"
            elif "admin" in title_lower or "controller" in title_lower:
                role = "operations"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": None,
            "email": email,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news articles from Oxy Capital WordPress posts.

    Oxy Capital uses WordPress and exposes posts via the REST API.
    This extractor fetches posts from /wp-json/wp/v2/posts endpoint.
    """
    news = []
    seen_urls = set()

    # First try: monitor fetched the WP API URL directly.
    parsed_json = _parse_wp_posts_json(html)
    if parsed_json:
        return parsed_json

    # The monitor fetches the WP API URL via URLS["news"] and passes the response
    # to _parse_wp_posts_json() above. No standalone requests.get() fallback needed —
    # bypassing the monitor's rate limiter/circuit breaker causes reliability issues (M3 audit fix).

    # Fallback: try to extract from individual post page HTML using JSON-LD
    soup = BeautifulSoup(html, "html.parser")

    # Look for Yoast JSON-LD structured data (common on WordPress)
    json_ld_script = soup.find("script", {"type": "application/ld+json", "class": "yoast-schema-graph"})
    if json_ld_script:
        try:
            data = json.loads(json_ld_script.string)
            graph = data.get("@graph", [])

            for item in graph:
                item_type = item.get("@type", "")
                if item_type in ["BlogPosting", "Article", "WebPage"]:
                    title = item.get("name") or item.get("headline", "")
                    if not title or len(title) < 10:
                        continue

                    url = item.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    # Parse date
                    date = None
                    date_published = item.get("datePublished", "")
                    if date_published:
                        try:
                            dt = datetime.fromisoformat(date_published.replace("Z", "+00:00"))
                            date = dt.strftime("%Y-%m-%d")
                        except:
                            pass

                    summary = item.get("description", "")
                    if summary and len(summary) > 200:
                        summary = summary[:200] + "..."

                    news.append({
                        "title": title,
                        "url": url,
                        "date": date,
                        "summary": summary,
                        "confidence": 0.85,
                    })
        except:
            pass

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
