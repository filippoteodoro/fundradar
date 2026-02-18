"""Site-specific extractors for iblacapital.com."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "iblacapital.com"



# URL paths — verified against live site
URLS = {
    "portfolio": "/it/portfolio/",
    "team": None,
    "news": "/news/",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Ibla Capital page.

    Portfolio companies are in h1 elements with strong/b tags,
    with links to /portfolio_page/{company}/ pages.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Pattern 1: h1 elements with company names (strong/b wrapped)
    for h1 in soup.select("h1"):
        # Get text with separator to handle br tags
        name = h1.get_text(separator=" ", strip=True)
        # Clean up multiple spaces
        name = re.sub(r'\s+', ' ', name).strip()

        if not name or len(name) < 2 or name.lower() in seen_names:
            continue

        # Skip duplicate-word entries like "Assio Assio"
        words = name.split()
        if len(words) == 2 and words[0].lower() == words[1].lower():
            continue

        # Skip if looks like a person name (has first/last pattern with no company suffix)
        words = name.split()
        if len(words) == 2 and all(w[0].isupper() and w[1:].islower() for w in words if w):
            # Could be a person name, check for nearby portfolio_page link
            parent = h1.find_parent()
            if parent:
                link = parent.find("a", href=re.compile(r"/portfolio_page/"))
                if link:
                    href = link.get("href", "")
                    # If the slug contains a person-like pattern, skip
                    slug = href.split("/")[-2] if href.endswith("/") else href.split("/")[-1]
                    if "-" in slug and len(slug.split("-")) == 2:
                        # Likely a person (first-last pattern)
                        continue

        seen_names.add(name.lower())

        # Look for link to portfolio page in nearby content
        detail_url = None
        container = h1.find_parent(class_="wpb_wrapper") or h1.find_parent()
        if container:
            link = container.find_previous("a", href=re.compile(r"/portfolio_page/"))
            if link:
                detail_url = urljoin(base_url, link.get("href", ""))

        companies.append({
            "name": name,
            "sector": None,
            "website": detail_url,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    # Pattern 2: Links to portfolio_page for companies
    if not companies:
        for link in soup.select("a[href*='/portfolio_page/']"):
            href = link.get("href", "")
            # Extract company name from URL slug
            slug = href.rstrip("/").split("/")[-1]
            name = slug.replace("-", " ").title()

            if len(name) < 2 or name.lower() in seen_names:
                continue

            # Skip person-like slugs
            if len(name.split()) == 2:
                continue

            seen_names.add(name.lower())

            companies.append({
                "name": name,
                "sector": None,
                "website": urljoin(base_url, href),
                "description": None,
                "status": "current",  # Portfolio page entries
                "confidence": 0.75,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Ibla Capital page.

    Team members are in article.mix elements with portfolio_category_65,
    names in h5.portfolio_title a.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Pattern 1: Portfolio-style cards (category 65 = team)
    for article in soup.select("article.mix"):
        # Get the name from h5.portfolio_title
        name_el = article.select_one("h5.portfolio_title a")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue

        seen_names.add(name.lower())

        # Extract photo URL
        photo_url = None
        img = article.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        # Extract profile URL
        profile_url = name_el.get("href")
        if profile_url:
            profile_url = urljoin(base_url, profile_url)

        members.append({
            "name": name,
            "title": None,  # Not available on list page
            "role": None,
            "linkedin": None,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.90,
        })

    # Pattern 2: Fallback - links to portfolio_page with person names
    if not members:
        for link in soup.select("a[href*='/portfolio_page/']"):
            href = link.get("href", "")
            # Extract name from URL slug
            slug = href.rstrip("/").split("/")[-1]
            words = slug.split("-")

            # Person names typically have 2-3 parts
            if 2 <= len(words) <= 3:
                name = " ".join(w.title() for w in words)

                if name.lower() in seen_names:
                    continue

                seen_names.add(name.lower())

                members.append({
                    "name": name,
                    "title": None,
                    "role": None,
                    "linkedin": None,
                    "email": None,
                    "photo_url": None,
                    "confidence": 0.75,
                })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Ibla Capital news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Pattern: News/blog post entries
    for article in soup.select("article, .post, .news-item, .blog-post"):
        title_el = article.select_one("h2 a, h3 a, h4 a, h5 a, .entry-title a")
        if not title_el:
            title_el = article.select_one("h2, h3, h4, h5, .entry-title")

        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 5 or title.lower() in seen_titles:
            continue

        seen_titles.add(title.lower())

        # Extract URL
        url = None
        if title_el.name == "a":
            url = title_el.get("href")
        else:
            link = article.select_one("a[href]")
            if link:
                url = link.get("href")
        if url:
            url = urljoin(base_url, url)

        # Extract date
        date = None
        date_el = article.select_one("time, .date, .entry-date, [datetime]")
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
