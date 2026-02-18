"""Site-specific extractors for www.macquarie.com."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.macquarie.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/it/en/about/company/macquarie-asset-management/our-portfolio.html",
    "team": None,
    "news": ["/it/en/about/news.html", "/it/en/about/company/macquarie-asset-management/news.html"],
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Macquarie Asset Management.

    Structure:
    - Companies are listed as cards with h4 headings
    - Links go to individual company pages under our-portfolio/
    - Each link contains company name + description concatenated
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Find all portfolio company links
    for link in soup.select('a[href*="our-portfolio/"]'):
        href = link.get("href", "")

        # Skip the main portfolio page itself
        if href.endswith("our-portfolio.html"):
            continue

        # Get h4 inside the link for company name
        h4 = link.select_one("h4")
        if h4:
            name = h4.get_text(strip=True)
        else:
            # Fallback: extract from link text before description
            full_text = link.get_text(strip=True)
            # Company names are typically title case before lowercase description
            match = re.match(r'^([A-Z][^a-z]*[a-z]+(?:\s+[A-Z][a-z]+)*)', full_text)
            if match:
                name = match.group(1)
            else:
                # Try extracting from URL
                match = re.search(r'/([^/]+)\.html$', href)
                if match:
                    name = match.group(1).replace("-", " ").title()
                else:
                    continue

        if not name or len(name) < 2:
            continue

        # Skip duplicates
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Get description from paragraph or span
        description = None
        desc_el = link.select_one("p, span.description")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        # If no separate description, try to extract from concatenated text
        if not description:
            full_text = link.get_text(strip=True)
            if name in full_text:
                desc_part = full_text.replace(name, "", 1).strip()
                if desc_part:
                    description = desc_part[:500]

        # Extract sector from description if possible
        sector = None
        sector_keywords = {
            "telecom": "Telecommunications",
            "airport": "Transportation",
            "rail": "Transportation",
            "highway": "Transportation",
            "toll road": "Transportation",
            "data center": "Technology",
            "digital": "Technology",
            "solar": "Renewable Energy",
            "wind": "Renewable Energy",
            "energy": "Energy",
            "water": "Utilities",
            "waste": "Waste Management",
            "recycling": "Waste Management",
            "hospital": "Healthcare",
            "healthcare": "Healthcare",
            "parking": "Real Estate",
            "hotel": "Real Estate",
            "housing": "Real Estate",
            "residential": "Real Estate",
            "chemical": "Chemicals",
            "fertiliser": "Agriculture",
            "agriculture": "Agriculture",
        }
        if description:
            desc_lower = description.lower()
            for keyword, sector_name in sector_keywords.items():
                if keyword in desc_lower:
                    sector = sector_name
                    break

        # Build company website from portfolio URL
        website = urljoin(base_url, href)

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,  # Link to their portfolio page entry
            "description": description,
            "status": "current",  # Portfolio page entries
            "confidence": 0.90,
        })

    return companies


def extract_news(html: str, base_url: str) -> list[dict]:
    """
    Extract news articles from Macquarie news pages.

    Handles both:
    - /it/en/about/news.html (general news, more Italy-relevant content)
    - /it/en/about/company/macquarie-asset-management/news.html (MAM-specific)
    """
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_urls = set()
    seen_titles = set()

    # Month name mapping for date parsing
    month_map = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
    }

    # Date patterns
    year_pattern = re.compile(r'/news/(\d{4})/')
    full_date_re = re.compile(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(\d{4})",
        re.IGNORECASE,
    )

    # Find all links to news articles
    for link in soup.find_all("a", href=lambda x: x and "/news/" in x):
        href = link.get("href", "")

        # Must point to an actual article (has year in path)
        if not year_pattern.search(href):
            continue

        # Skip if already seen
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Get title from link text
        title = link.get_text(strip=True)

        # Skip if title is too short
        if not title or len(title) < 10:
            continue

        # Skip navigation/UI text
        title_lower = title.lower()
        if any(skip in title_lower for skip in ["back to", "read more", "view all", "see all"]):
            continue

        # Skip exact "News" or "All news" links
        if title_lower.strip() in ("news", "all news", "latest news"):
            continue

        # Dedup by title prefix
        title_key = title_lower[:50]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Try to extract full date from nearby text
        date = None
        parent = link.find_parent(["div", "li", "article", "section"])
        if parent:
            text = parent.get_text(" ", strip=True)
            dm = full_date_re.search(text)
            if dm:
                day, month_name, year = dm.groups()
                mn = month_map.get(month_name.lower())
                if mn:
                    date = f"{year}-{mn}-{day.zfill(2)}"

        # Fallback: extract year from URL
        if not date:
            year_match = year_pattern.search(href)
            if year_match:
                date = f"{year_match.group(1)}-01-01"

        news.append({
            "title": title,
            "url": full_url,
            "date": date,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "news": extract_news,
}
