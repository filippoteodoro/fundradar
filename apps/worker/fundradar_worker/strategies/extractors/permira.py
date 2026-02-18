"""Site-specific extractors for permira.com (Permira)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
import urllib.request
import urllib.error

DOMAIN = "www.permira.com"

# Portfolio fetched from /api/portfolio (paginated, Italy-filtered) — not from HTML.
# HTML shell page rarely changes even when API data does.
ALWAYS_EXTRACT = True

# URL paths for monitoring - verified against live site
# Note: Portfolio uses API at /api/portfolio, page path is for fallback HTML
URLS = {
    "portfolio": "/investing/buyout",
    "team": "/people",
    "news": ["/news-and-insights/announcements/", "/news-and-insights/in-the-news/"],
}
# API endpoint for portfolio pagination
PORTFOLIO_API = "https://www.permira.com/api/portfolio"
PORTFOLIO_FILTER = '{"countryRegion":["italy"]}'


def _fetch_api_page(page: int) -> dict | None:
    """Fetch a page from Permira's portfolio API (Italy filter)."""
    url = f"{PORTFOLIO_API}?page={page}&filters={PORTFOLIO_FILTER}&sort=a_z"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _parse_company(company: dict, base_url: str) -> dict | None:
    """Parse a company from API/HTML data into our standard format."""
    if not isinstance(company, dict):
        return None

    name = company.get("name") or company.get("title", "")
    if not name or len(name) < 2:
        return None

    # In Permira's data, description contains sector/industry
    sector = company.get("description", "")
    if isinstance(sector, dict):
        sector = sector.get("text", "")

    # Get detail page URL from cta.link.url
    website = None
    cta = company.get("cta")
    if isinstance(cta, dict):
        link = cta.get("link")
        if isinstance(link, dict):
            url = link.get("url")
            if url:
                website = urljoin(base_url, url)

    return {
        "name": name,
        "sector": sector if sector else None,
        "website": website,
        "description": None,
        "status": "current",  # API Italy filter only returns current holdings
        "confidence": 0.85,
    }


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Permira portfolio page.

    Uses the API with Italy country filter for all pages to get
    only Italian portfolio companies consistently.
    Falls back to __NEXT_DATA__ if the API is unavailable.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    def add_company(company_data: dict) -> bool:
        """Add a company if not already seen. Returns True if added."""
        parsed = _parse_company(company_data, base_url)
        if not parsed:
            return False
        name_lower = parsed["name"].lower()
        if name_lower in seen_names:
            return False
        seen_names.add(name_lower)
        companies.append(parsed)
        return True

    # Strategy 1: Use the API with Italy filter for all pages (consistent filtering)
    first_page = _fetch_api_page(0)
    if first_page and "data" in first_page:
        for company in first_page["data"]:
            add_company(company)

        total_items = first_page.get("totalItems", 0)
        items_per_page = first_page.get("itemsPerPage", 20)
        if items_per_page > 0 and total_items > items_per_page:
            total_pages = (total_items + items_per_page - 1) // items_per_page
            for page in range(1, total_pages):
                api_data = _fetch_api_page(page)
                if api_data and "data" in api_data:
                    for company in api_data["data"]:
                        add_company(company)

    # Strategy 2: Fallback to __NEXT_DATA__ if API returned nothing
    if not companies:
        next_data = soup.select_one("script#__NEXT_DATA__")
        if next_data:
            try:
                data = json.loads(next_data.string)
                contents = data.get("props", {}).get("initialProps", {}).get("pageProps", {}).get("Contents", [])

                for item in contents:
                    if not isinstance(item, dict):
                        continue

                    # Check for portfolio data (note: 'portoflios' is misspelled in the API)
                    for key in ["portoflios", "portfolios", "companies", "portfolio", "investments"]:
                        if key in item:
                            portfolio_data = item[key]
                            if isinstance(portfolio_data, dict):
                                if "data" in portfolio_data:
                                    portfolio_data = portfolio_data["data"]

                            if isinstance(portfolio_data, list):
                                for company in portfolio_data:
                                    add_company(company)

            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Permira people page.

    Note: Team data is in __NEXT_DATA__ JSON on /people/meet-our-people page.
    The data is paginated (456 total, 16 per page across 28 pages).
    This extractor gets the first page of results from the initial HTML.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    next_data = soup.select_one("script#__NEXT_DATA__")
    if not next_data:
        return members

    try:
        data = json.loads(next_data.string)
        contents = data.get("props", {}).get("initialProps", {}).get("pageProps", {}).get("Contents", [])

        # Look for peoples data (usually in Contents[2])
        for item in contents:
            if not isinstance(item, dict):
                continue

            peoples = item.get("peoples")
            if peoples and isinstance(peoples, dict):
                people_data = peoples.get("data", [])

                for person in people_data:
                    if not isinstance(person, dict):
                        continue

                    name = person.get("name", "").strip()
                    if not name or len(name) < 3 or name.lower() in seen_names:
                        continue

                    seen_names.add(name.lower())

                    title = person.get("title", "").strip() or None

                    # Extract photo URL
                    photo_url = None
                    image = person.get("image")
                    if isinstance(image, dict):
                        photo_url = image.get("url")

                    # Determine role from title
                    role = None
                    if title:
                        title_lower = title.lower()
                        if "partner" in title_lower:
                            if "managing" in title_lower or "senior" in title_lower:
                                role = "partner"
                            else:
                                role = "partner"
                        elif "principal" in title_lower:
                            role = "principal"
                        elif "director" in title_lower:
                            role = "director"
                        elif "vice president" in title_lower or "vp" in title_lower:
                            role = "vp"
                        elif "associate" in title_lower:
                            role = "associate"
                        elif "analyst" in title_lower:
                            role = "analyst"

                    members.append({
                        "name": name,
                        "title": title,
                        "role": role,
                        "linkedin": None,
                        "email": None,
                        "photo_url": photo_url,
                        "confidence": 0.90,
                    })

    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Permira announcements/in-the-news pages.

    The __NEXT_DATA__ JSON has articles at:
      props.pageProps.Contents[N].news.data[]
    Each article: title, link.url (or cta.link.url), publishingDate
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    next_data = soup.select_one("script#__NEXT_DATA__")
    if not next_data:
        return news

    try:
        data = json.loads(next_data.string)

        # Try both possible paths: pageProps may exist but lack Contents (Playwright-rendered)
        # initialProps.pageProps always has the full data
        contents = []
        for path in [
            data.get("props", {}).get("pageProps", {}),
            data.get("props", {}).get("initialProps", {}).get("pageProps", {}),
        ]:
            contents = path.get("Contents", [])
            if contents:
                break

        for item in contents:
            if not isinstance(item, dict):
                continue

            # Look for article data in any dict value that has a "data" list
            for key in ["news", "pressReleases", "articles", "pageTeaserGroup"]:
                container = item.get(key)
                if not container:
                    continue

                # Handle nested data arrays
                articles = []
                if isinstance(container, dict) and "data" in container:
                    articles = container["data"]
                elif isinstance(container, list):
                    articles = container

                for article in articles:
                    if not isinstance(article, dict):
                        continue

                    title = article.get("title") or article.get("name", "")
                    if not title or len(title) < 5:
                        continue

                    if title.lower() in seen_titles:
                        continue
                    seen_titles.add(title.lower())

                    # Extract URL from multiple possible locations
                    url = None
                    for link_key in ["link", "url", "cta"]:
                        link_val = article.get(link_key)
                        if isinstance(link_val, dict):
                            link_val = link_val.get("link", link_val)
                            if isinstance(link_val, dict):
                                link_val = link_val.get("url")
                        if isinstance(link_val, str) and link_val:
                            url = urljoin(base_url, link_val)
                            break

                    # Extract date from multiple possible fields
                    date = article.get("publishingDate") or \
                           article.get("date") or \
                           article.get("publishedAt")

                    news.append({
                        "title": title,
                        "url": url,
                        "date": date,
                        "summary": None,
                        "confidence": 0.85,
                    })

    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
