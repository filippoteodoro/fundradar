"""Site-specific extractors for cdpventurecapital.it.

NOTE: CDP Venture Capital's portfolio page uses flip cards with data attributes.
Some company names contain legal suffixes, secondary brand names after dashes,
or duplicate name fragments that need cleaning.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.cdpventurecapital.it"

def _clean_cdp_company_name(name: str) -> str:
    """Clean up messy CDP Venture Capital portfolio company names.

    Handles patterns like:
    - "Connexa InsTech Srl e Connexa" -> "Connexa InsTech"
    - "Flyer Tech Srl - Transactionale" -> "Flyer Tech"
    - "Volumeet S.r.l. - Musify" -> "Volumeet"
    - "Company Name Srl" -> "Company Name"
    - "I'm ok Holding" -> left as-is (legitimate name)
    """
    # Strip leading/trailing whitespace
    name = name.strip()

    # Remove everything after " - " (secondary brand/product names)
    # e.g. "Volumeet S.r.l. - Musify" -> "Volumeet S.r.l."
    # e.g. "Flyer Tech Srl - Transactionale" -> "Flyer Tech Srl"
    if " - " in name:
        name = name.split(" - ")[0].strip()

    # Remove " e " + repeated company name fragment
    # e.g. "Connexa InsTech Srl e Connexa" -> "Connexa InsTech Srl"
    e_match = re.search(r'\s+e\s+\w+$', name, re.IGNORECASE)
    if e_match:
        suffix = e_match.group().strip().lstrip("e ").strip()
        # Only remove if the suffix is a substring of the preceding name
        preceding = name[:e_match.start()]
        if suffix.lower() in preceding.lower():
            name = preceding.strip()

    # Strip Italian legal suffixes: S.r.l., Srl, S.p.A., SpA, S.r.l, etc.
    name = re.sub(
        r'\s+(?:S\.?r\.?l\.?|S\.?p\.?A\.?|S\.?a\.?s\.?|S\.?n\.?c\.?|'
        r'S\.?c\.?a\.?r\.?l\.?|S\.?c\.?r\.?l\.?|Srl|SpA|SPA|SRL)\.?\s*$',
        '', name, flags=re.IGNORECASE
    ).strip()

    return name

# URL paths for monitoring (verified against live site)
URLS = {
    "portfolio": "/it/portfolio.page",
    "team": "/it/management.page",
    "news": "/it/newsroom.page",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from CDP Venture Capital portfolio page.

    Structure: .flip-card-wrapper elements with data attributes for sector,
    category, region. Inside: h4.h4 for name, .btn-animated-icon-grey for website,
    .sector div for sector label.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find card wrappers with data attributes
    wrappers = soup.select(".flip-card-wrapper")

    for wrapper in wrappers:
        # Skip supported funds / co-investment vehicles — not portfolio companies
        category = wrapper.get("data-category", "")
        if category == "FondiSupportati":
            continue

        # Get name from h4
        h4 = wrapper.find("h4", class_="h4")
        if not h4:
            continue

        name = h4.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Clean up messy names (legal suffixes, secondary brands, fragments)
        name = _clean_cdp_company_name(name)
        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get sector from data attribute or .sector div
        sector = wrapper.get("data-settore", "").strip()
        if not sector:
            sector_div = wrapper.find("div", class_="sector")
            if sector_div:
                sector = sector_div.get_text(strip=True)
        sector = sector if sector and sector.lower() != "other" else None

        # Get investment category
        category = wrapper.get("data-category", "")
        # "InvestimentoDiretto" = direct investment, "FondiSupportati" = supported funds

        # Get region
        region = wrapper.get("data-regione", "").strip()
        if region and region.lower() == "altro":
            region = None

        # Get website from link
        website = None
        link = wrapper.find("a", class_="btn-animated-icon-grey", href=True)
        if link:
            href = link.get("href", "")
            if href and not href.startswith("#"):
                website = href if href.startswith("http") else urljoin(base_url, href)

        # Get logo/image URL
        img = wrapper.find("img")
        logo_url = None
        if img:
            src = img.get("src")
            if src:
                logo_url = src if src.startswith("http") else urljoin(base_url, src)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": "current",  # Portfolio page entries
            "confidence": 0.85,
        })

    # Strategy 2: Fallback to alternative selectors if primary fails
    if not companies:
        # Try various common portfolio card patterns
        for selector in [".investment-card", ".portfolio-card", ".company-card",
                         "div[data-company]", ".card-item", ".grid-item"]:
            for card in soup.select(selector):
                h4 = card.find(["h4", "h3", "h2"])
                if h4:
                    name = _clean_cdp_company_name(h4.get_text(strip=True))
                    if name and len(name) > 1 and name.lower() not in seen_names:
                        seen_names.add(name.lower())
                        companies.append({
                            "name": name,
                            "sector": None,
                            "website": None,
                            "description": None,
                            "status": "current",  # Portfolio page entries
                            "confidence": 0.70,
                        })

    # Strategy 3: Look for any card with company-like content
    if not companies:
        for card in soup.find_all("div", class_=re.compile(r"card|portfolio|company|startup", re.I)):
            heading = card.find(["h3", "h4", "h5", "strong"])
            if heading:
                name = _clean_cdp_company_name(heading.get_text(strip=True))
                # Filter out navigation and generic text
                if (name and len(name) > 2 and len(name) < 100
                    and name.lower() not in seen_names
                    and not any(skip in name.lower() for skip in ["menu", "filter", "cerca", "search", "cookie"])):
                    seen_names.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": None,
                        "description": None,
                        "status": "current",  # Portfolio page entries
                        "confidence": 0.60,
                    })

    # Dedup: remove entries where one name is a substring of another
    # Handles "Talent Garden Med" vs "Talent Garden" — keep the shorter canonical name
    companies = _dedup_cdp_names(companies)

    return companies

def _dedup_cdp_names(companies: list[dict]) -> list[dict]:
    """Remove duplicate entries where one name is a variant/substring of another.

    For CDP, the shorter name is typically the canonical one (e.g., "Talent Garden"
    is the real company, "Talent Garden Med" is a sub-entity/variant).
    """
    if len(companies) <= 1:
        return companies

    # Normalize for comparison
    def norm(n: str) -> str:
        return re.sub(r'[^a-z0-9\s]', '', n.lower()).strip()

    indexed = [(c, norm(c["name"])) for c in companies]
    to_remove = set()

    for i, (ci, ni) in enumerate(indexed):
        if i in to_remove:
            continue
        for j, (cj, nj) in enumerate(indexed):
            if i == j or j in to_remove:
                continue
            # Check if one is a prefix/substring of the other
            shorter, longer = (ni, nj) if len(ni) <= len(nj) else (nj, ni)
            shorter_idx, longer_idx = (i, j) if len(ni) <= len(nj) else (j, i)
            if len(shorter) >= 4 and shorter != longer and longer.startswith(shorter):
                # For CDP, keep the shorter (canonical) name — the longer is a variant
                to_remove.add(longer_idx)

    return [c for i, (c, _) in enumerate(indexed) if i not in to_remove]

def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from CDP Venture Capital management page.

    Structure: Names with titles and LinkedIn links.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for LinkedIn links to find team member sections
    for linkedin_link in soup.find_all("a", href=re.compile(r"linkedin\.com/in/", re.I)):
        linkedin_url = linkedin_link.get("href", "")

        # Find parent container
        parent = linkedin_link.find_parent(["div", "section", "article", "li"])
        if not parent:
            continue

        # Find name in heading
        name = None
        for heading in parent.find_all(["h3", "h4", "h5", "strong"]):
            text = heading.get_text(strip=True)
            if text and len(text) >= 3:
                # Basic name check
                words = text.split()
                if len(words) >= 2 and all(w[0].isupper() for w in words if w):
                    name = text
                    break

        if not name:
            # Try to get name from text near LinkedIn link
            for el in parent.find_all(["p", "span", "div"]):
                text = el.get_text(strip=True)
                if text and len(text) >= 3 and len(text) < 50:
                    words = text.split()
                    if len(words) >= 2 and len(words) <= 4:
                        name = text
                        break

        if not name:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Find title
        title = None
        for el in parent.find_all(["p", "span"]):
            text = el.get_text(strip=True)
            if text and text.lower() != name_lower and len(text) < 100:
                if any(t in text.lower() for t in ["direttore", "responsabile", "manager", "director", "head"]):
                    title = text
                    break
                elif not title and len(text) > 5:
                    title = text

        # Get photo
        photo_url = None
        img = parent.find("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src and "svg" not in src.lower():
                photo_url = urljoin(base_url, src)

        # Determine role from title
        role = None
        if title:
            title_lower = title.lower()
            if any(r in title_lower for r in ["ceo", "amministratore delegato", "direttore generale"]):
                role = "partner"
            elif "direttore" in title_lower or "director" in title_lower:
                role = "director"
            elif any(r in title_lower for r in ["responsabile", "head of", "manager"]):
                role = "manager"
            elif any(r in title_lower for r in ["associate", "analyst", "analista"]):
                role = "associate"

        members.append({
            "name": name,
            "title": title,
            "role": role,
            "linkedin": linkedin_url,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members

def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from CDP Venture Capital newsroom page.
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Italian date pattern
    date_pattern = re.compile(r"(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+(\d{4})", re.I)

    for heading in soup.find_all(["h3", "h4"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 15:
            continue

        # Skip navigation
        title_lower = title.lower()
        if any(skip in title_lower for skip in ["newsroom", "news", "menu", "filter", "cerca"]):
            continue

        # Skip duplicates
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Find link
        url = None
        parent_link = heading.find_parent("a", href=True)
        if parent_link:
            url = urljoin(base_url, parent_link.get("href", ""))
        else:
            link = heading.find("a", href=True)
            if link:
                url = urljoin(base_url, link.get("href", ""))

        # Find date
        date = None
        parent = heading.find_parent(["article", "div", "li"])
        if parent:
            text = parent.get_text()
            match = date_pattern.search(text)
            if match:
                day, month, year = match.groups()
                month_num = _MONTH_NAMES.get(month.lower(), "01")
                date = f"{year}-{month_num}-{day.zfill(2)}"

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": None,
            "confidence": 0.80,
        })

    return news

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
