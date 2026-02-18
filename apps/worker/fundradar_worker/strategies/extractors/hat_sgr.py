"""Site-specific extractors for hat.it.

HAT SGR is an Italian private equity fund focused on mid-market companies.
Portfolio companies are listed at /portfolio/our-partnership/
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "hat.it"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio/our-partnership/",
    "team": "/people/our-team/",
    "news": None,  # News is on homepage
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from HAT SGR our-partnership page.

    Structure: article.teaser-partner elements with:
    - h2/h3/h4: Company name
    - a[href]: Link to detail page
    - img: Logo image
    - .thor-partner-badge: Fund and sector info
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for article in soup.select("article.teaser-partner"):
        # Get company name from heading
        name_el = article.select_one("h2, h3, h4")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from cat-pills spans (second one is sector, first is fund)
        sector = None
        pills = article.select("span.cat-pills")
        if len(pills) >= 2:
            # Second pill is the sector
            sector = pills[1].get_text(strip=True)
        elif len(pills) == 1:
            # Only one pill - check if it's a sector (not "HAT X")
            pill_text = pills[0].get_text(strip=True)
            if not pill_text.startswith("HAT"):
                sector = pill_text

        # Get logo URL
        logo_url = None
        img = article.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                logo_url = urljoin(base_url, src)

        # Get detail page URL
        detail_url = None
        link = article.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href and "hat.it" in href:
                detail_url = href

        companies.append({
            "name": name,
            "sector": sector,
            "website": detail_url,
            "description": None,
            "logo_url": logo_url,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    # Dedup: remove entries whose normalized name is a variant of another.
    # Handles: "Burke Burke" vs "BURKE & BURKE", "Mech I Tronic" vs "MECH-I-TRONIC",
    # "Primat 2" vs "PRIMAT", "Safety21 2" vs "SAFETY21".
    companies = _dedup_hat_names(companies)

    return companies


def _normalize_hat_name(name: str) -> str:
    """Normalize a HAT SGR company name for dedup comparison.

    Strips numeric suffixes, punctuation, special chars, and ALL whitespace
    to collapse variants like 'MECH-I-TRONIC' and 'Mech I Tronic'.
    """
    n = name.lower().strip()
    # Remove trailing numeric suffixes like " 2", " 3"
    n = re.sub(r'\s+\d+$', '', n)
    # Remove ALL non-alphanumeric chars (including spaces, hyphens, ampersands)
    n = re.sub(r'[^a-z0-9]', '', n)
    return n


def _has_numeric_suffix(name: str) -> bool:
    """Check if name has a trailing numeric suffix like ' 2', ' 3'."""
    return bool(re.search(r'\s+\d+$', name.strip()))


def _dedup_hat_names(companies: list[dict]) -> list[dict]:
    """Remove duplicate entries where normalized names match.

    When two entries normalize to the same string, keep the one WITHOUT
    a numeric suffix (e.g., keep "PRIMAT" over "Primat 2"). If neither
    has a suffix, keep the longer original name (more information).
    """
    if len(companies) <= 1:
        return companies

    # Group by normalized name
    groups: dict[str, list[tuple[int, dict]]] = {}
    for i, c in enumerate(companies):
        norm = _normalize_hat_name(c["name"])
        if norm not in groups:
            groups[norm] = []
        groups[norm].append((i, c))

    keep_indices = set()
    for norm, entries in groups.items():
        if len(entries) == 1:
            keep_indices.add(entries[0][0])
        else:
            # Prefer entries WITHOUT numeric suffix, then longest original name
            best = min(entries, key=lambda e: (
                _has_numeric_suffix(e[1]["name"]),  # False (0) < True (1)
                -len(e[1]["name"]),  # Longer names first
            ))
            keep_indices.add(best[0])

    # Second pass: check if any kept normalized name is a substring of another
    kept = [(i, companies[i], _normalize_hat_name(companies[i]["name"]))
            for i in sorted(keep_indices)]
    to_remove = set()
    for a_idx, (i, ci, ni) in enumerate(kept):
        if i in to_remove:
            continue
        for b_idx, (j, cj, nj) in enumerate(kept):
            if i == j or j in to_remove:
                continue
            shorter, longer = (ni, nj) if len(ni) <= len(nj) else (nj, ni)
            shorter_orig_idx = i if len(ni) <= len(nj) else j
            if len(shorter) >= 3 and shorter != longer and shorter in longer:
                to_remove.add(shorter_orig_idx)

    return [c for i, c in enumerate(companies) if i in keep_indices and i not in to_remove]


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from HAT SGR team page.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    for article in soup.select("article.teaser-team, .team-member"):
        name_el = article.select_one("h2, h3, h4, .name")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        title = None
        title_el = article.select_one(".title, .role, .position")
        if title_el:
            title = title_el.get_text(strip=True)

        role = None
        if title:
            title_lower = title.lower()
            if "partner" in title_lower or "founder" in title_lower:
                role = "partner"
            elif "director" in title_lower:
                role = "director"
            elif "manager" in title_lower:
                role = "manager"
            elif "associate" in title_lower or "analyst" in title_lower:
                role = "associate"

        photo_url = None
        img = article.select_one("img")
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
            "confidence": 0.85,
        })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news/press items from HAT SGR news page.

    Structure:
    - article.teaser-post contains each news item
    - div.post-info has category and date (concatenated, e.g., "Portfolio News22-01-2026")
    - a inside header has the title and URL
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select("article.teaser-post"):
        # Get title and URL from a in header
        header = item.select_one("header")
        if not header:
            continue

        title_link = header.select_one("a")
        if not title_link:
            continue

        title = title_link.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Get URL
        url = None
        href = title_link.get("href")
        if href:
            url = urljoin(base_url, href)

        # Get category and date from post-info (format: "Portfolio News22-01-2026")
        date = None
        category = None
        post_info = header.select_one("div.post-info")
        if post_info:
            info_text = post_info.get_text(strip=True)
            # Date is at the end in DD-MM-YYYY format
            date_match = re.search(r"(\d{2}-\d{2}-\d{4})$", info_text)
            if date_match:
                date = date_match.group(1)
                # Category is everything before the date
                category = info_text[:date_match.start()].strip()

        # Use category as summary
        summary = category if category else None

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
