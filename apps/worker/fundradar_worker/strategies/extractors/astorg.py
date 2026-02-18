"""Site-specific extractors for astorg.com (Astorg Partners)."""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.astorg.com"

# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/investments",
    "team": "/team",
    "news": "/news",
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Astorg investments page.
    
    Site may use JavaScript rendering - multiple fallback strategies.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Strategy 1: Look for investment links
    for link in soup.find_all("a", href=re.compile(r"/investments/[^/?#]+")):
        href = link.get("href", "")
        slug = href.rstrip("/").split("/")[-1]
        
        if not slug or slug == "investments":
            continue
        
        # Get name from link text or convert slug
        name = link.get_text(strip=True)
        if not name or len(name) < 2:
            name = slug.replace("-", " ").title()
        
        if name.lower() in seen_names:
            continue
            
        # Skip navigation items
        if any(skip in name.lower() for skip in ["view all", "see more", "filter"]):
            continue
            
        seen_names.add(name.lower())
        
        companies.append({
            "name": name,
            "sector": None,
            "website": urljoin(base_url, href),
            "description": None,
            "status": "current",
            "confidence": 0.85,
        })

    # Strategy 2: Look for company cards
    if not companies:
        for card in soup.find_all(class_=re.compile(r"card|portfolio|investment", re.I)):
            heading = card.find(["h2", "h3", "h4", "strong"])
            if heading:
                name = heading.get_text(strip=True)
                if name and len(name) > 2 and len(name) < 80 and name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    
                    link = card.find("a", href=True)
                    website = urljoin(base_url, link.get("href", "")) if link else None
                    
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": website,
                        "description": None,
                        "status": "current",
                        "confidence": 0.75,
                    })

    # Strategy 3: Look for any meaningful content structure
    if not companies:
        for item in soup.find_all(["article", "div", "li"], class_=re.compile(r"item|entry", re.I)):
            heading = item.find(["h2", "h3", "h4"])
            if heading:
                name = heading.get_text(strip=True)
                if (name and len(name) > 2 and len(name) < 80
                    and name.lower() not in seen_names
                    and not any(skip in name.lower() for skip in ["menu", "filter", "astorg", "news"])):
                    seen_names.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": None,
                        "description": None,
                        "status": "current",
                        "confidence": 0.60,
                    })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members from Astorg team page."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Strategy 1: Look for team member links
    for link in soup.find_all("a", href=re.compile(r"/team/[^/?#]+")):
        href = link.get("href", "")
        slug = href.rstrip("/").split("/")[-1]
        
        if not slug or slug == "team":
            continue
        
        name = link.get_text(strip=True)
        if not name or len(name) < 3:
            name = slug.replace("-", " ").title()
        
        # Validate as a person name
        words = name.split()
        if len(words) < 2:
            continue
            
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
            "confidence": 0.80,
        })

    # Strategy 2: Look for team member cards
    if not members:
        for card in soup.find_all(class_=re.compile(r"team|member|person", re.I)):
            name_el = card.find(["h2", "h3", "h4", "strong"])
            if name_el:
                name = name_el.get_text(strip=True)
                words = name.split()
                if len(words) >= 2 and name.lower() not in seen_names:
                    seen_names.add(name.lower())
                    
                    title = None
                    title_el = card.find(class_=re.compile(r"title|role|position"))
                    if title_el:
                        title = title_el.get_text(strip=True)
                    
                    members.append({
                        "name": name,
                        "title": title,
                        "role": None,
                        "linkedin": None,
                        "email": None,
                        "photo_url": None,
                        "confidence": 0.75,
                    })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news from Astorg news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Look for news links
    for link in soup.find_all("a", href=re.compile(r"/news/[^/?#]+")):
        href = link.get("href", "")
        
        # Get title from link text
        title = link.get_text(strip=True)
        if not title or len(title) < 15 or title.lower() in seen_titles:
            continue
            
        # Skip navigation
        if any(skip in title.lower() for skip in ["view all", "see more", "filter", "older", "newer"]):
            continue
            
        seen_titles.add(title.lower())
        
        news.append({
            "title": title,
            "url": urljoin(base_url, href),
            "date": None,
            "summary": None,
            "confidence": 0.80,
        })

    # Also look for article elements
    for article in soup.select("article, .news-item"):
        title_el = article.find(["h2", "h3", "h4"])
        if not title_el:
            continue
            
        title = title_el.get_text(strip=True)
        if not title or len(title) < 15 or title.lower() in seen_titles:
            continue
            
        seen_titles.add(title.lower())
        
        link = article.find("a", href=True)
        url = urljoin(base_url, link.get("href", "")) if link else None
        
        date_el = article.select_one("time, .date")
        date = date_el.get("datetime") or date_el.get_text(strip=True) if date_el else None
        
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
