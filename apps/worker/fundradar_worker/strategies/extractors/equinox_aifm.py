"""Site-specific extractors for www.equinox-investments.com (Equinox AIFM)."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json

DOMAIN = "www.equinox-investments.com"



# URL paths for monitoring - verified against live site
URLS = {
    "portfolio": "/portfolio",
    "team": None,  # No dedicated team page found
    "news": "/news",
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Equinox portfolio page.

    Data is in __NEXT_DATA__ JSON with projects having "title" for company name.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    # Try to extract from __NEXT_DATA__ JSON
    next_data = soup.select_one("script#__NEXT_DATA__")
    if next_data:
        try:
            data = json.loads(next_data.string)
            # Navigate to portfolio data
            page_data = data.get("props", {}).get("pageProps", {}).get("data", {})

            # Look for projects in various locations
            def find_projects(obj, found=None):
                if found is None:
                    found = []
                if isinstance(obj, dict):
                    if "title" in obj and isinstance(obj.get("title"), str):
                        # Check if this looks like a company entry
                        title = obj["title"]
                        if len(title) > 2 and title not in ["Portfolio", "Name", "Fund", "Stake",
                                                            "Sector", "Headquarters", "Status", "Website"]:
                            found.append(obj)
                    for v in obj.values():
                        find_projects(v, found)
                elif isinstance(obj, list):
                    for item in obj:
                        find_projects(item, found)
                return found

            projects = find_projects(page_data)

            for proj in projects:
                name = proj.get("title", "").strip()
                if not name or len(name) < 2 or name.lower() in seen_names:
                    continue

                # Skip table headers, generic text, and HTML content
                if name in ["2016 - today", "Name", "Fund", "Stake", "Sector",
                           "Headquarters", "Status", "Website", "Websites"]:
                    continue
                # Skip if it looks like HTML or intro text
                if "<" in name or "Equinox has" in name or len(name) > 50:
                    continue
                # Skip year ranges like "2011-2015"
                if re.match(r'^\d{4}-\d{4}$', name) or re.match(r'^\d{4} - \d{4}$', name):
                    continue
                # Skip social media links
                if "Equinox Facebook" in name or "Equinox Twitter" in name or "Equinox LinkedIn" in name:
                    continue

                seen_names.add(name.lower())

                companies.append({
                    "name": name,
                    "sector": None,
                    "website": None,
                    "description": None,
                    "status": "current",  # Portfolio page entries
                    "confidence": 0.85,
                })

        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: Look for company patterns in HTML
    if not companies:
        # Try pattern matching on text
        text = soup.get_text()
        # Look for company names that appear multiple times (title + table)
        potential_names = re.findall(r'"title":"([A-Z][a-zA-Z0-9\s&]+)"', html)
        for name in potential_names:
            name = name.strip()
            if len(name) > 2 and name.lower() not in seen_names:
                if name not in ["Portfolio", "Name", "Fund", "Stake", "Sector",
                               "Headquarters", "Status", "Website"]:
                    seen_names.add(name.lower())
                    companies.append({
                        "name": name,
                        "sector": None,
                        "website": None,
                        "description": None,
                        "status": "current",  # Portfolio page entries
                        "confidence": 0.75,
                    })

    return companies


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members from Equinox team page.

    Data is in embedded JSON with "name" for person's name and "category" for role.
    """
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen_names = set()

    # Try to extract from __NEXT_DATA__ JSON
    next_data = soup.select_one("script#__NEXT_DATA__")
    if next_data:
        try:
            data = json.loads(next_data.string)

            # Find team members in the JSON structure
            def find_members(obj, found=None):
                if found is None:
                    found = []
                if isinstance(obj, dict):
                    # Check if this looks like a team member entry
                    if "name" in obj and "category" in obj:
                        category = obj.get("category", "")
                        if category in ["InvestmentTeam", "AssetManager", "SeniorAdvisor"]:
                            found.append(obj)
                    for v in obj.values():
                        find_members(v, found)
                elif isinstance(obj, list):
                    for item in obj:
                        find_members(item, found)
                return found

            team_members = find_members(data)

            for member in team_members:
                name = member.get("name", "").strip()
                if not name or len(name) < 3 or name.lower() in seen_names:
                    continue

                # Skip file names
                if "." in name and any(ext in name.lower() for ext in [".jpg", ".png", ".mp4"]):
                    continue

                seen_names.add(name.lower())

                # Extract category as role
                category = member.get("category", "")
                title = None
                role = None
                if category == "InvestmentTeam":
                    role = "investment"
                    title = "Investment Team"
                elif category == "AssetManager":
                    role = "operations"
                    title = "Asset Manager"
                elif category == "SeniorAdvisor":
                    role = "advisor"
                    title = "Senior Advisor"

                # Try to extract description for better title
                description = member.get("description", "")
                if description:
                    # Strip HTML tags
                    clean_desc = re.sub(r'<[^>]+>', ' ', description)
                    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
                    # Look for title patterns at start (stop before "Joined")
                    title_match = re.search(r'^([A-Za-z\s&]+(?:Partner|Director|Manager|Analyst|Officer|Advisor|team))',
                                           clean_desc, re.IGNORECASE)
                    if title_match:
                        title = title_match.group(1).strip()
                        # Clean up HTML entities
                        title = title.replace("&amp;", "&")

                # Extract photo
                photo_url = None
                media = member.get("media", {})
                if isinstance(media, dict):
                    url = media.get("url")
                    if url:
                        photo_url = url

                members.append({
                    "name": name,
                    "title": title,
                    "role": role,
                    "linkedin": None,
                    "email": None,
                    "photo_url": photo_url,
                    "confidence": 0.90,
                })

        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: Pattern matching on HTML
    if not members:
        # Find "name" patterns that look like person names
        name_matches = re.findall(r'"name":"([A-Z][a-z]+ [A-Z][a-z]+)"', html)
        for name in name_matches:
            name = name.strip()
            if len(name) > 3 and name.lower() not in seen_names:
                # Skip file names
                if not any(ext in name.lower() for ext in [".jpg", ".png", ".mp4"]):
                    seen_names.add(name.lower())
                    members.append({
                        "name": name,
                        "title": None,
                        "role": None,
                        "linkedin": None,
                        "email": None,
                        "photo_url": None,
                        "confidence": 0.75,
                    })

    return members


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news items from Equinox news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    # Try __NEXT_DATA__ JSON
    next_data = soup.select_one("script#__NEXT_DATA__")
    if next_data:
        try:
            data = json.loads(next_data.string)

            # Find news items
            def find_news(obj, found=None):
                if found is None:
                    found = []
                if isinstance(obj, dict):
                    # Look for news item patterns
                    if "title" in obj and "date" in obj:
                        found.append(obj)
                    elif "title" in obj and "publishedAt" in obj:
                        found.append(obj)
                    for v in obj.values():
                        find_news(v, found)
                elif isinstance(obj, list):
                    for item in obj:
                        find_news(item, found)
                return found

            news_items = find_news(data)

            for item in news_items:
                title = item.get("title", "").strip()
                if not title or len(title) < 5 or title.lower() in seen_titles:
                    continue

                seen_titles.add(title.lower())

                date = item.get("date") or item.get("publishedAt")
                url = item.get("linkMedia") or item.get("url") or item.get("slug")
                if url and not url.startswith("http"):
                    url = urljoin(base_url, url)

                news.append({
                    "title": title,
                    "url": url,
                    "date": date,
                    "summary": None,
                    "confidence": 0.85,
                })

        except (json.JSONDecodeError, KeyError):
            pass

    return news


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
    "news": extract_news,
}
