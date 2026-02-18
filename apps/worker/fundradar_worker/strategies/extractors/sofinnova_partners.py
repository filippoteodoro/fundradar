"""Site-specific extractors for sofinnovapartners.com.

Sofinnova Partners is a leading European life sciences venture capital firm
founded in 1972, with over €4 billion under management. They have multiple
investment strategies including Capital, MD Start, Crossover, Industrial Biotech,
Telethon, Digital Medicine, and Biovelocita funds.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote

DOMAIN = "sofinnovapartners.com"  # Note: www redirects to non-www

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio",
    "team": "/team",
    "news": "/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies from Sofinnova Partners portfolio page.

    Companies are displayed in a grid with links to /portfolio/{slug}.
    Each link contains fund name in first <p> and company name in second <p>.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Portfolio links have href starting with /portfolio/
    for link in soup.select("a[href^='/portfolio/']"):
        href = link.get("href", "")
        if not href or href == "/portfolio":
            continue

        # Extract company name and fund from paragraphs
        paragraphs = link.select("p")
        if len(paragraphs) < 2:
            # Try getting text directly
            name = link.get_text(strip=True)
            fund = None
        else:
            fund = paragraphs[0].get_text(strip=True)
            name = paragraphs[1].get_text(strip=True)

        if not name:
            continue

        # Clean up name - remove arrow indicators
        name = re.sub(r'\s*→\s*', '', name)
        name = name.strip()

        if not name or len(name) < 2:
            continue

        # Normalize and deduplicate
        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Determine sector based on fund
        sector = "Healthcare"  # Default for life sciences VC
        if fund:
            fund_lower = fund.lower()
            if "industrial" in fund_lower or "biotech" in fund_lower:
                sector = "Industrial Biotech"
            elif "digital" in fund_lower:
                sector = "Digital Health"
            elif "md start" in fund_lower:
                sector = "Medical Devices"

        # Build portfolio URL
        portfolio_url = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": None,
            "description": None,
            "fund": fund if fund else None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    # Dedup: remove entries whose normalized name is a substring of another entry's name.
    # Handles cases like "Inspirna Rgenix" vs "Inspirna", "Dbv Technologies" vs "DBV",
    # "Nucana Biomed" vs "NuCana", and entries with numeric suffixes like "CompanyX 2".
    companies = _dedup_substring_names(companies)

    return companies


def _normalize_for_dedup(name: str) -> str:
    """Normalize a company name for dedup comparison."""
    n = name.lower().strip()
    # Remove trailing numeric suffixes like " 2", " 3"
    n = re.sub(r'\s+\d+$', '', n)
    # Remove common suffixes that cause false duplicates
    n = re.sub(r'\s+(biomed|technologies|therapeutics|pharma|biosciences?)$', '', n)
    # Collapse whitespace and strip non-alphanumeric (keep spaces)
    n = re.sub(r'[^a-z0-9\s]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def _dedup_substring_names(companies: list[dict]) -> list[dict]:
    """Remove entries where one name is a substring/variant of another.

    - When normalized names differ and one is a substring of the other,
      keep the longer/more specific normalized name.
    - When normalized names are identical (e.g., "NuCana" and "Nucana Biomed"
      both normalize to "nucana"), keep the entry with the shorter original name
      (the cleaner form without the stripped suffix).
    """
    if len(companies) <= 1:
        return companies

    # Build normalized name index
    indexed = [(c, _normalize_for_dedup(c["name"])) for c in companies]

    to_remove = set()
    for i, (ci, ni) in enumerate(indexed):
        if i in to_remove:
            continue
        for j, (cj, nj) in enumerate(indexed):
            if i == j or j in to_remove:
                continue
            # If one normalized name is a substring of the other
            shorter, longer = (ni, nj) if len(ni) <= len(nj) else (nj, ni)
            shorter_idx, longer_idx = (i, j) if len(ni) <= len(nj) else (j, i)
            if len(shorter) >= 3 and shorter in longer:
                if ni == nj:
                    # Identical normalized names: keep the shorter original name
                    # (it's the cleaner form without garbage suffixes like " 2")
                    if len(ci["name"]) <= len(cj["name"]):
                        to_remove.add(j)
                    else:
                        to_remove.add(i)
                else:
                    # Different normalized names: keep the longer/more specific one
                    to_remove.add(shorter_idx)

    return [c for i, (c, _) in enumerate(indexed) if i not in to_remove]


def _split_camelcase_name(combined: str) -> str:
    """Split a CamelCase combined name into separate words.

    Example: "AntoinePapiernik" -> "Antoine Papiernik"
    """
    # Insert space before uppercase letters that follow lowercase
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', combined)


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Sofinnova Partners team page.

    Team members are displayed in cards with links to /team/{slug}.
    Structure: <p>FirstLast</p><p>Title</p>
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Team member links have href starting with /team/
    for link in soup.select("a[href^='/team/']"):
        href = link.get("href", "")
        if not href or href == "/team":
            continue

        # Extract name and title from paragraphs
        paragraphs = link.select("p")
        if len(paragraphs) >= 2:
            # First p has concatenated name, second has title
            raw_name = paragraphs[0].get_text(strip=True)
            title = paragraphs[1].get_text(strip=True)
            # Split the concatenated name
            name = _split_camelcase_name(raw_name)
        else:
            # Fallback: parse from full text
            text = link.get_text(" ", strip=True)
            if not text or len(text) < 5:
                continue
            name = text
            title = None

        if not name or len(name) < 3:
            continue

        # Skip duplicates
        if name in seen_names:
            continue
        seen_names.add(name)

        # Get photo URL from image
        photo_url = None
        img = link.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                photo_url = urljoin(base_url, src)

        # Determine role category from title
        # The title starts with the role, e.g., "Partner, Sofinnova Partners - Capital"
        role = None
        if title:
            title_lower = title.lower()
            # Check role at start of title (before comma)
            role_part = title_lower.split(",")[0].strip()
            if "chairman" in role_part or "managing partner" in role_part:
                role = "partner"
            elif role_part == "partner" or role_part.startswith("partner"):
                role = "partner"
            elif "principal" in role_part:
                role = "principal"
            elif "senior associate" in role_part:
                role = "senior_associate"
            elif "associate" in role_part:
                role = "associate"
            elif "analyst" in role_part:
                role = "analyst"
            elif "director" in role_part or "head of" in role_part:
                role = "director"
            elif "cfo" in role_part or "general counsel" in role_part:
                role = "executive"
            elif "manager" in role_part:
                role = "staff"

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
    """Extract news articles from Sofinnova Partners news page.

    News items are links to /news/{slug} with title text.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_urls = set()

    # News links have href starting with /news/
    for link in soup.select("a[href^='/news/']"):
        href = link.get("href", "")
        if not href or href == "/news":
            continue

        # Get title from text content
        text = link.get_text(" ", strip=True)
        if not text or len(text) < 10:
            continue

        # Some links have "News DD Month, YYYY" prefix - extract date
        date = None
        title = text
        date_match = re.search(r"News\s+(\d{1,2}\s+\w+,?\s+\d{4})", text)
        if date_match:
            date = date_match.group(1)
            # Remove date prefix from title
            title = text[date_match.end():].strip()

        if not title or len(title) < 10:
            # Use decoded URL as title fallback
            title = unquote(href.split("/news/")[-1]).replace("-", " ").replace("%20", " ")
            title = re.sub(r'\s+', ' ', title).strip()

        # Build full URL
        url = urljoin(base_url, href)

        # Skip duplicates
        if url in seen_urls:
            continue
        seen_urls.add(url)

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
