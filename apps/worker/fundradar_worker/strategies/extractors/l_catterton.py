"""Site-specific extractors for lcatterton.com.

L Catterton - Global consumer-focused private equity firm.
Portfolio companies shown as logo grid with fund type/status in classes.
Team members organized by team group (Leadership, Investment, etc.).
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.lcatterton.com"



# URL paths — verified against live site
URLS = {
    "portfolio": "/Investments.html",
    "team": "/People.html",
    "news": "/Press.html",
}
def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from L Catterton press page.

    Structure:
    - a.news-highlight: 2 featured items at top
    - div.press-newslist a: main listing with <span>MM.DD</span><p>title</p>
    - mytype attribute: "Transactions" or "In the News"
    - href is hash-based (#!/slug)
    - div.press-year: year header for each year section
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    def _fix_brand_name(text: str) -> str:
        """Fix 'LC atterton' / 'LCatterton' artifacts from stylized HTML rendering."""
        return re.sub(r"\bLC\s*atterton\b", "L Catterton", text)

    # Strategy 1: Main press listing (div.press-newslist a) — bulk of content
    current_year = None
    for holder in soup.select("div.press-listing-holder"):
        # Get year from press-year div
        year_div = holder.select_one("div.press-year")
        if year_div:
            year_text = year_div.get_text(strip=True)
            if year_text.isdigit():
                current_year = year_text

        for item in holder.select("div.press-newslist a"):
            # Get title from <p> element
            p = item.find("p")
            title = p.get_text(strip=True) if p else item.get_text(strip=True)
            title = _fix_brand_name(title)
            if not title or len(title) < 10:
                continue

            title_lower = title.lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            # Get date from <span> (MM.DD format) + year from section
            date = None
            span = item.find("span")
            if span and current_year:
                date_text = span.get_text(strip=True)
                # Parse MM.DD format
                parts = date_text.split(".")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    month = parts[0].zfill(2)
                    day = parts[1].zfill(2)
                    date = f"{current_year}-{month}-{day}"

            # Get URL (hash-based)
            url = None
            href = item.get("href")
            if href:
                url = urljoin(base_url, "Press.html" + href)

            news.append({
                "title": title,
                "url": url,
                "date": date,
                "summary": None,
                "confidence": 0.85,
            })

    # Strategy 2: Featured highlights (a.news-highlight) — fallback if main listing empty
    if not news:
        for item in soup.select("a.news-highlight"):
            content_div = item.select_one(".news-content")
            if not content_div:
                continue

            date = None
            date_div = content_div.select_one(".date")
            if date_div:
                date = date_div.get_text(strip=True)
                date_div.extract()

            title = _fix_brand_name(content_div.get_text(strip=True))
            if not title or len(title) < 10:
                continue

            title_lower = title.lower()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            url = None
            href = item.get("href")
            if href:
                url = urljoin(base_url, "Press.html" + href)

            news.append({
                "title": title,
                "url": url,
                "date": date,
                "summary": None,
                "confidence": 0.85,
            })

    return news


def _slug_to_name_fallback(slug: str) -> str:
    """Convert slug to readable name as fallback when detail page is unavailable."""
    name = slug
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    name = name.replace("-", " ").replace("_", " ")
    name = " ".join(word.capitalize() for word in name.split())
    return name


def _fetch_detail_page_names(slugs: list[str], base_url: str) -> dict[str, str]:
    """Fetch proper company names from detail pages (Investments-{slug}.html).

    Each detail page has the real company name in the <title> tag.
    Rate-limited to 0.2s between requests to avoid overwhelming the server.
    """
    import time
    try:
        import requests as _req
    except ImportError:
        return {}

    mapping: dict[str, str] = {}
    base = base_url.rstrip("/")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FundRadar/1.0)"}

    for slug in slugs:
        url = f"{base}/Investments-{slug}.html"
        try:
            resp = _req.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                # Extract name from <title> tag (fastest, no full parse needed)
                import re as _re
                title_match = _re.search(r"<title>([^<]+)</title>", resp.text)
                if title_match:
                    name = title_match.group(1).strip()
                    if name and len(name) > 1 and name.lower() not in ("investments", "l catterton"):
                        mapping[slug] = name
        except Exception:
            pass
        time.sleep(0.2)

    return mapping


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from L Catterton investments page.

    Structure:
    - .brands-logo-holder contains all company links
    - Each <a> has classes for fund type (Growth, Flagship_Buyout, etc.) and status (current/historical)
    - href contains company slug like #!/x/x/companyname
    - img has logo URL but NO alt text; links have NO text content
    - Proper names are fetched from detail pages (Investments-{slug}.html)
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    # First pass: collect all slugs
    slug_data: list[tuple[str, list, str]] = []  # (slug, classes, href)
    for a in soup.select(".brands-logo-holder a"):
        classes = a.get("class", [])
        href = a.get("href", "")
        parts = href.split("/")
        slug = parts[-1] if parts else ""
        if not slug or slug in seen:
            continue
        seen.add(slug)
        slug_data.append((slug, classes, href))

    # Fetch proper names from detail pages
    all_slugs = [s for s, _, _ in slug_data]
    slug_names = _fetch_detail_page_names(all_slugs, base_url)

    for slug, classes, href in slug_data:
        # Use detail page name if available, otherwise fallback to slug conversion
        name = slug_names.get(slug) or _slug_to_name_fallback(slug)

        if not name or len(name) < 2:
            continue
        if len(name) > 80:
            continue

        # Determine status from classes
        if "current" in classes:
            status = "current"
        elif "historical" in classes:
            status = "exited"
        else:
            status = None

        sector = None

        # Get logo URL
        logo_url = None
        a_tag = soup.select_one(f'.brands-logo-holder a[href$="/{slug}"]')
        if a_tag:
            img = a_tag.select_one("img")
            if img:
                src = img.get("src") or img.get("loadme")
                if src:
                    logo_url = urljoin(base_url, src)

        profile_url = urljoin(base_url, "Investments.html" + href) if href else None

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "status": status,
            "logo_url": logo_url,
            "profile_url": profile_url,
            "confidence": 0.95,
        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from L Catterton people page.

    Structure:
    - .people-team containers hold each team group
    - .title inside each group has the team name
    - .person links have member names and bio hrefs
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    for team_div in soup.select(".people-team"):
        # Find title inside group
        title_div = team_div.select_one(".title")
        group_name = title_div.get_text(strip=True) if title_div else None

        # Extract people in this group
        for person_link in team_div.select(".person"):
            name = person_link.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            # Skip if not a person name (at least 2 name parts)
            if len(name.split()) < 2:
                continue

            # Dedupe
            name_lower = name.lower()
            if name_lower in seen:
                continue
            seen.add(name_lower)

            href = person_link.get("href", "")
            profile_url = urljoin(base_url, "People.html" + href) if href else None

            # Map group to role
            role = None
            if group_name:
                group_lower = group_name.lower()
                if "leadership" in group_lower:
                    role = "partner"
                elif "investment" in group_lower:
                    role = "investment_team"
                elif "senior advisor" in group_lower:
                    role = "advisor"

            members.append({
                "name": name,
                "title": group_name,
                "role": role,
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "profile_url": profile_url,
                "confidence": 0.85,
            })

    return members


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
