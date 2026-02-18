"""Site-specific extractors for towerbrook.com (TowerBrook)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.towerbrook.com"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/investments/",
    "team": "/our-team/",
    "news": "/news/",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from TowerBrook investments page.
    
    Structure:
    - Company name in elements with class "el-title"
    - Website links have class "uk-button" pointing to company domains
    - Companies grouped by sector in accordion sections
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Strategy 1: Find company cards/items with el-title class
    for title_el in soup.find_all(class_=re.compile(r"el-title")):
        name = title_el.get_text(strip=True)
        if not name or len(name) < 2 or name.lower() in seen_names:
            continue
        
        # Skip section headers
        if any(skip in name.lower() for skip in ["business services", "consumer", "financial", "healthcare", "technology", "industrials"]):
            continue
            
        seen_names.add(name.lower())
        
        # Find the parent container to get sector and website
        parent = title_el.find_parent(["div", "article", "li"])
        
        # Get website from nearby uk-button link
        website = None
        if parent:
            link = parent.find("a", class_="uk-button", href=True)
            if link:
                href = link.get("href", "")
                if href and href.startswith("http"):
                    website = href
        
        # Try to determine sector from parent accordion section
        sector = None
        accordion = title_el.find_parent(class_=re.compile(r"accordion|section"))
        if accordion:
            # Look for sector heading
            sector_heading = accordion.find(class_=re.compile(r"heading|title"))
            if sector_heading:
                sector_text = sector_heading.get_text(strip=True)
                if any(s in sector_text.lower() for s in ["business", "consumer", "financial", "healthcare", "technology"]):
                    sector = sector_text
        
        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": "current",
            "confidence": 0.90,
        })

    # Strategy 2: Fallback - look for company website links
    if not companies:
        for link in soup.find_all("a", class_="uk-button", href=True):
            href = link.get("href", "")
            if not href.startswith("http") or "towerbrook" in href.lower():
                continue
            
            # Find company name from nearby title element
            parent = link.find_parent(["div", "article", "li"])
            if parent:
                title_el = parent.find(class_=re.compile(r"title"))
                if title_el:
                    name = title_el.get_text(strip=True)
                    if name and len(name) > 1 and name.lower() not in seen_names:
                        seen_names.add(name.lower())
                        companies.append({
                            "name": name,
                            "sector": None,
                            "website": href,
                            "description": None,
                            "status": "current",
                            "confidence": 0.80,
                        })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from TowerBrook team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Look for team member cards
    for card in soup.find_all(class_=re.compile(r"team|member|person|profile", re.I)):
        name_el = card.find(["h2", "h3", "h4", "strong", ".name"])
        if not name_el:
            continue
            
        name = name_el.get_text(strip=True)
        if not name or len(name) < 3 or name.lower() in seen_names:
            continue
            
        # Validate as a person name
        words = name.split()
        if len(words) < 2:
            continue
            
        seen_names.add(name.lower())
        
        # Get title
        title = None
        title_el = card.find(class_=re.compile(r"title|role|position"))
        if title_el:
            title = title_el.get_text(strip=True)
        
        # Determine role category
        role = None
        if title:
            title_lower = title.lower()
            if "co-founder" in title_lower or "founder" in title_lower:
                role = "founder"
            elif "managing partner" in title_lower or "senior partner" in title_lower:
                role = "partner"
            elif "partner" in title_lower:
                role = "partner"
            elif "managing director" in title_lower:
                role = "director"
            elif "director" in title_lower:
                role = "director"
            elif "principal" in title_lower:
                role = "principal"
            elif "vice president" in title_lower:
                role = "vp"
            elif "associate" in title_lower:
                role = "associate"
        
        # Get photo
        photo_url = None
        img = card.find("img")
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
    """Extract news from TowerBrook news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for article in soup.select("article, .news-item, [class*='post']"):
        title_el = article.find(["h2", "h3", "h4"])
        if not title_el:
            continue
            
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
            
        seen_titles.add(title.lower())
        
        # Get link
        url = None
        link = article.find("a", href=True)
        if link:
            url = urljoin(base_url, link.get("href", ""))
        
        # Get date
        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)
        
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
