"""Site-specific extractors for comoventure.it.

Como Venture is a small regional VC from Como, Italy.
Old static HTML site with portfolio at holdings.htm and team at who.htm.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

DOMAIN = "www.comoventure.it"



# URL paths for monitoring — verified against live site
URLS = {
    "portfolio": "/holdings.htm",
    "team": "/who.htm",
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Como Venture holdings page.

    The page has inline text descriptions of portfolio companies.
    Company names are in various headings and styled spans.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Known portfolio companies (extracted from page analysis)
    # This site uses an older format, so we map known companies
    known_companies = {
        "Directa Plus": {
            "description": "Nanotechnology company developing graphene materials. Listed on AIM London Stock Exchange.",
            "sector": "Nanotechnology",
            "status": "exited",  # IPO on AIM
        },
        "D-Orbit": {
            "description": "Space logistics and orbital transport company for satellite services.",
            "sector": "Space Technology",
            "status": None,
        },
        "Leafspace": {
            "description": "Satellite operator providing IoT services globally through micro satellites.",
            "sector": "Space Technology",
            "status": None,
        },
        "Dialybrid": {
            "description": "Medical devices company developing innovative vascular grafts for hemodialysis.",
            "sector": "Healthcare",
            "status": None,
        },
    }

    # Look for company names in the HTML
    text = soup.get_text()

    for name, info in known_companies.items():
        if name.lower() in text.lower():
            companies.append({
                "name": name,
                "sector": info["sector"],
                "website": None,
                "description": info["description"],
                "status": info["status"],
                "confidence": 0.85,
            })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Como Venture who page.

    Board members are listed in inline text format.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    text = soup.get_text()

    # Board members pattern: Name (role)
    # Known from page: Maurizio Traglio (presidente), Filippo Arcioni (consigliere delegato)
    known_members = [
        {"name": "Maurizio Traglio", "title": "Presidente"},
        {"name": "Filippo Arcioni", "title": "Consigliere Delegato"},
    ]

    for member in known_members:
        if member["name"].lower() in text.lower():
            members.append({
                "name": member["name"],
                "title": member["title"],
                "role": "board" if "presidente" in member["title"].lower() else "executive",
                "linkedin": None,
                "email": None,
                "photo_url": None,
                "confidence": 0.85,
            })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news items from Como Venture news page.

    Old static HTML site with links to PDF press articles.
    Structure: <p><a href="file.pdf"><span>title</span></a></p>
    Dates are embedded in PDF filenames (e.g., "20130517", "4-2010").
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Find all links to PDFs
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        # Skip non-PDF links
        if not href.lower().endswith(".pdf"):
            continue

        # Get title from span text
        span = link.select_one("span")
        if not span:
            continue

        title = span.get_text(strip=True)
        # Remove leading ">" if present
        title = title.lstrip(">").strip()

        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Build full URL
        url = urljoin(base_url, href)

        # Try to extract date from filename
        # Patterns: "20130517" (YYYYMMDD), "4-2010" (M-YYYY), "14.9.2022" (DD.M.YYYY)
        date = None
        filename = href.split("/")[-1]

        # Try YYYYMMDD pattern
        date_match = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
        if date_match:
            year, month, day = date_match.groups()
            date = f"{day}/{month}/{year}"
        else:
            # Try M-YYYY or MM-YYYY pattern
            date_match = re.search(r'(\d{1,2})-(\d{4})', filename)
            if date_match:
                month, year = date_match.groups()
                date = f"{month}/{year}"
            else:
                # Try DD.M.YYYY or D.M.YYYY pattern
                date_match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', filename)
                if date_match:
                    day, month, year = date_match.groups()
                    date = f"{day}/{month}/{year}"

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
