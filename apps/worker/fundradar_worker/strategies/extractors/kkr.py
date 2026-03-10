"""Site-specific extractors for kkr.com (KKR & Co.).

KKR's portfolio page uses server-side pagination (15 items/page, ~20 pages).
We fetch all pages from their JSON API to get the full portfolio (~296 companies).
Falls back to HTML table parsing if the API isn't available.
"""
import re
import json
import logging
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

DOMAIN = "www.kkr.com"

# This extractor fetches portfolio data from KKR's JSON API, not from the HTML page.
# The HTML shell page rarely changes even when the API data does, so we must always
# run extraction to detect new portfolio companies.
ALWAYS_EXTRACT = True

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/invest/portfolio",
    "team": "/about/our-people",
    "news": ["https://media.kkr.com/news-releases", "/insights"],
}

# Valid sectors from KKR's site (lowercase for matching)
VALID_SECTORS = {
    "consumer discretionary", "consumer staples", "energy", "financials",
    "healthcare", "industrials", "information technology", "materials",
    "communication services", "utilities", "real estate", "other",
}

# Region normalization
REGION_MAP = {
    "americas": "Americas",
    "europe, the middle east and africa": "EMEA",
    "emea": "EMEA",
    "asia pacific": "Asia Pacific",
    "asia": "Asia Pacific",
}

# Patterns that indicate garbage, not real companies
GARBAGE_PATTERNS = [
    # Cookie consent and toggle buttons
    r"^cookies?$",
    r"^performance\s*cookies?$",
    r"^targeting\s*cookies?$",
    r"^strictly\s*necessary",
    r"^functional\s*cookies?$",
    r"^analytics\s*cookies?$",
    # Cookie toggle buttons (more specific patterns)
    r"^\+enabled$",
    r"^\-disabled$",
    r"^\+active$",
    r"^\-inactive$"

    # Geolocation/consent notices and redirects
    r"^you\s+(appear|seem)\s+to\s+be",
    r"^we\s+(are\s+)?currently",
    r"located\s+in\s+(singapore|hong\s*kong|europe|asia)",
    r"^do\s+you\s+want\s+to\s+be\s+redirected",
    r"^take\s+me\s+to\s+kkr",
    r"^continue\s+browsing$",

    # Navigation/UI elements
    r"^(search|filter|menu|load\s+more|view\s+all|clear\s+filters?)$",
    r"^asset\s*class:?$",
    r"^industry:?$",
    r"^region:?$",
    r"^portfolio(\s+company)?:?$",
    r"^\d+\s*results?$",
    r"^\(\d+\)\s*results?$",
    r"^filter\s+by:?",
    r"^explore",
    r"^learn\s+more$",
    r"^company\s+directory$",
    r"^skip\s+to",
    r"^toggle\s+button$",
    r"^menu\s+toggle",
    r"^all\s+asset\s+classes?$",
    r"^health\s+care\s+growth$",

    # Site sections and navigation
    r"^about$",
    r"^approach$",
    r"^invest$",
    r"^insights?$",
    r"^careers?$",
    r"^contact",
    r"^subscribe",
    r"^investor\s+relations$",
    r"^client\s+portal$",
    r"^media\s+center$",
    r"^our\s+people$",
    r"^history$",
    r"^institutional\s+investors?$",
    r"^global\s+wealth$",
    r"^family\s+capital$",
    r"^ownership\s+cultures?$",
    r"^shared\s+success$",
    r"^delivering\s+better",
    r"^macro\s+insights?$",
    r"^investment\s+insights?$",
    r"^career\s+opportunities?$",
    r"^student\s+careers?$",
    r"^inclusive\s+culture$",
    r"^stay\s+connected",
    r"^here'?s\s+the\s+deal$",
    r"^investment\s+stories?$",
    r"^featured\s+insight$",

    # Marketing/descriptive text
    r"^a\s+leading\s+global",
    r"^a\s+network\s+of\s+expert",
    r"^our\s+portfolio",
    r"^supporting\s+our\s+investments",
    r"founded\s+in\s+\d{4}",

    # Footer/legal
    r"^privacy",
    r"^terms",
    r"^security",
    r"^compliance",
    r"^disclosures?$",
    r"^accessibility$",
    r"^manage\s+cookies$",
    r"^kohlberg\s+kravis",
    r"^\d{4}\s+kkr",
    r"^©",

    # Asset classes and sectors (not companies)
    r"^private\s+equity$",
    r"^global\s+impact$",
    r"^tech\s+growth$",
    r"^infrastructure$",
    r"^real\s+estate$",
    r"^credit$",
    r"^capital\s+markets$",
    r"^insurance$",
    r"^strategic\s+partnerships?$",
    r"^all\s+(industries|regions)$",
    r"^communication\s+services$",
    r"^consumer\s+discretionary$",
    r"^consumer\s+staples$",
    r"^energy$",
    r"^financials$",
    r"^healthcare$",
    r"^industrials$",
    r"^information\s+technology$",
    r"^materials$",
    r"^utilities$",
    r"^americas$",
    r"^asia\s*pacific$",
    r"^europe",
]

# Compile patterns for efficiency
GARBAGE_RE = [re.compile(p, re.IGNORECASE) for p in GARBAGE_PATTERNS]

# Companies that appear in KKR's API but belong to other funds or are misattributed.
# These should be excluded from KKR's portfolio.
EXCLUDED_COMPANIES = {
    "ensora health",
    "karo healthcare",
    "korean battery ess",
}

def _is_garbage(name: str) -> bool:
    """Check if a name is garbage (not a real company)."""
    if not name or len(name) < 2 or len(name) > 100:
        return True

    name_lower = name.lower().strip()

    # Excluded companies that belong to other funds
    if name_lower in EXCLUDED_COMPANIES:
        return True

    # Single common words that aren't companies
    single_word_garbage = {
        "portfolio", "company", "search", "filter", "menu", "about",
        "invest", "insights", "careers", "contact", "history", "people",
        "approach", "sustainability", "citizenship", "culture", "education",
        "subscribe", "locations", "disclosures", "accessibility", "compliance",
        "x",  # Close button
    }

    if name_lower in single_word_garbage:
        return True

    for pattern in GARBAGE_RE:
        if pattern.search(name_lower):
            return True

    # Must contain at least one letter
    if not re.search(r'[a-zA-Z]', name):
        return True

    return False

def _is_likely_company_name(name: str) -> bool:
    """Check if a string looks like a company name."""
    if _is_garbage(name):
        return False

    # Company names are typically 2-60 characters
    if len(name) < 2 or len(name) > 60:
        return False

    return True

def _fetch_portfolio_api(base_url: str) -> list[dict]:
    """Fetch all portfolio companies from KKR's paginated JSON API."""
    if not requests:
        logger.warning("requests library not available for KKR API fetch")
        return []

    api_path = "/content/kkr/sites/global/en/invest/portfolio/jcr:content/root/main-par/bioportfoliosearch.bioportfoliosearch.json"
    api_url = urljoin(base_url, api_path)

    companies = []
    seen_names = set()
    page = 1
    max_pages = 25  # Safety limit

    while page <= max_pages:
        try:
            resp = requests.get(
                api_url,
                params={"page": page},
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"KKR API page {page} failed: {e}")
            break

        total_pages = data.get("pages", 0)
        results = data.get("results", [])

        if not results:
            break

        for item in results:
            name = (item.get("name") or "").strip()
            if not name or len(name) < 2 or name.lower() in seen_names:
                continue
            if _is_garbage(name):
                continue

            seen_names.add(name.lower())

            # Normalize sector
            raw_industry = (item.get("industry") or "").strip()
            sector = raw_industry.title() if raw_industry else None

            # Normalize region
            raw_region = (item.get("region") or "").lower()
            region = None
            for region_key, region_val in REGION_MAP.items():
                if region_key in raw_region:
                    region = region_val
                    break

            # Clean description (strip HTML tags)
            raw_desc = item.get("description") or ""
            desc = re.sub(r"<[^>]+>", "", raw_desc).strip() or None

            companies.append({
                "name": name,
                "sector": sector,
                "website": item.get("url") or None,
                "description": desc,
                "status": "current",
                "confidence": 0.95,
                "region": region,
            })

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)  # Rate limit

    logger.info(f"KKR API: fetched {len(companies)} companies across {page} pages")
    return companies

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from KKR.

    Strategy 1 (preferred): Fetch all pages from KKR's JSON API (~296 companies).
    Strategy 2 (fallback): Parse the first-page HTML table (only ~15 companies).
    """
    # Strategy 1: JSON API (all pages)
    companies = _fetch_portfolio_api(base_url)
    if companies:
        return companies

    # Strategy 2: HTML table fallback (first page only)
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        is_header = True

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            first_cell_text = cells[0].get_text(strip=True)
            if is_header and first_cell_text.lower() == "portfolio company":
                is_header = False
                continue

            raw_name = cells[0].get_text()
            name = raw_name.replace('\\n', ' ').replace('\\t', ' ')
            name = re.sub(r'\s+', ' ', name).strip()

            if "HQ" in name or len(name) > 80:
                continue

            if len(cells) > 1:
                raw_second = cells[1].get_text()
                second_cell = raw_second.replace('\\n', ' ').replace('\\t', ' ')
                second_cell = re.sub(r'\s+', ' ', second_cell).strip()
                if second_cell.startswith("HQ") or "HQ " in second_cell or "Website" in second_cell:
                    continue
                second_lower = second_cell.lower()
                asset_classes = {
                    "private equity", "tech growth", "global impact",
                    "health care growth", "infrastructure", "real estate",
                    "credit", "core infrastructure",
                }
                if second_lower not in asset_classes and not any(ac in second_lower for ac in asset_classes):
                    continue

            if _is_garbage(name):
                continue
            if not name or name.lower() in seen_names:
                continue

            seen_names.add(name.lower())

            sector = None
            region = None
            for cell in cells[1:]:
                cell_text = cell.get_text(strip=True).lower()
                if cell_text in VALID_SECTORS and not sector:
                    sector = cell_text.title()
                if not region:
                    for region_key, region_val in REGION_MAP.items():
                        if region_key in cell_text:
                            region = region_val
                            break

            companies.append({
                "name": name,
                "sector": sector,
                "website": None,
                "description": None,
                "status": "current",
                "confidence": 0.90,
                "region": region,
            })

    logger.info(f"Extracted {len(companies)} companies from KKR (HTML fallback)")
    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from KKR people page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Strategy 1: Look for person cards/profiles
    for card in soup.select(".person-card, .team-member, [class*='person'], [class*='profile']"):
        name_el = card.find(["h2", "h3", "h4", "strong", ".name"])
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue

        # Basic name validation (should have at least 2 words)
        words = name.split()
        if len(words) < 2:
            continue

        seen_names.add(name.lower())

        # Get title
        title = None
        title_el = card.select_one(".title, .role, .position, [class*='title']")
        if title_el:
            title = title_el.get_text(strip=True)

        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if any(x in title_lower for x in ["co-founder", "founder", "co-chairman", "chairman"]):
                role = "founder"
            elif any(x in title_lower for x in ["partner", "managing director"]):
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "principal" in title_lower:
                role = "principal"
            elif "associate" in title_lower:
                role = "associate"

        # Get photo
        photo_url = None
        img = card.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src and "placeholder" not in src.lower():
                photo_url = urljoin(base_url, src)

        # Get LinkedIn if available
        linkedin = None
        linkedin_link = card.find("a", href=re.compile(r"linkedin\.com/in/", re.I))
        if linkedin_link:
            linkedin = linkedin_link.get("href")

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    # Strategy 2: Look for names in a people list/grid
    if not members:
        for link in soup.find_all("a", href=re.compile(r"/about/our-people/[^/?#]+")):
            href = link.get("href", "")
            name_text = link.get_text(strip=True)

            if name_text and len(name_text.split()) >= 2 and name_text.lower() not in seen_names:
                seen_names.add(name_text.lower())
                members.append({
                    "name": name_text,
                    "title": None,
                    "role": None,
                    "linkedin": None,
                    "email": None,
                    "photo_url": None,
                    "confidence": 0.70,
                })

    logger.info(f"Extracted {len(members)} team members from KKR")
    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news from KKR press releases (media.kkr.com) and insights page.

    media.kkr.com is a SvelteKit SPA with press releases about deals.
    www.kkr.com/insights has thought leadership articles.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Month map for date parsing

    # Strategy 1: Press release items (media.kkr.com or any structured news page)
    # Look for links with news_id parameters or /news-details paths
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        title = link.get_text(strip=True)

        # Skip non-news links
        if not title or len(title) < 15 or len(title) > 250:
            continue
        if any(skip in title.lower() for skip in [
            "filter", "search", "subscribe", "sign up", "load more",
            "view all", "cookie", "privacy", "terms",
        ]):
            continue

        # Accept links to news details or press releases
        is_news_link = (
            "news_id=" in href
            or "/news-details" in href
            or "/news-releases/" in href
            or "businesswire.com" in href
            or "globenewswire.com" in href
        )
        if not is_news_link:
            continue

        title_lower = title.lower()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        url = urljoin(base_url, href)

        # Try to find date nearby
        date = None
        parent = link.find_parent(["div", "li", "article", "tr"])
        if parent:
            text = parent.get_text(" ", strip=True)
            # Match "Month DD, YYYY" or "DD Month YYYY"
            date_match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
            if date_match:
                month_name, day, year = date_match.groups()
                month_num = _MONTH_NAMES.get(month_name.lower(), "01")
                if month_num:
                    date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.85,
        })

    # Strategy 2: Article/insight cards (www.kkr.com/insights)
    if not news:
        for card in soup.select("article, .insight-card, .news-item, [class*='article']"):
            title_el = card.find(["h2", "h3", "h4"])
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title or len(title) < 10 or title.lower() in seen_titles:
                continue

            if any(skip in title.lower() for skip in ["filter", "search", "subscribe", "sign up"]):
                continue

            seen_titles.add(title.lower())

            url = None
            link = card.find("a", href=True)
            if link:
                url = urljoin(base_url, link.get("href", ""))

            date = None
            date_el = card.select_one("time, .date, [datetime]")
            if date_el:
                date = date_el.get("datetime") or date_el.get_text(strip=True)

            news.append({
                "title": title,
                "url": url,
                "date": date,
                "summary": None,
                "confidence": 0.80,
            })

    logger.info(f"Extracted {len(news)} news items from KKR")
    return news

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
