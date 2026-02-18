"""Site-specific extractors for sienna-pe.com (Sienna Private Equity).

European mid-market PE fund. Portfolio at /portfolio/ uses WordPress
with article.portfolio cards containing company names, descriptions,
acquisition dates, HQ, and employee counts.
"""
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.sienna-pe.com"


# URL paths — verified against live site
URLS = {
    "portfolio": "/portfolio/",
    "team": None,
    "news": None,
}


def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies from Sienna PE /portfolio/ page.

    Structure: article.portfolio elements with:
    - h2.post-title > a for company name and detail link
    - header > div > p for description
    - div.kpi-portfolio with date, country, employees
    - figure.fit-img > img for logo
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for article in soup.find_all("article", class_=lambda c: c and "portfolio" in str(c)):
        # Get company name from h2.post-title
        h2 = article.select_one("h2.post-title a")
        if not h2:
            h2 = article.select_one("h2.post-title")
        if not h2:
            continue

        name = h2.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Skip nav/section headers
        if name_lower in ("portfolio", "our portfolio", "investments"):
            continue

        # Get detail page URL
        website = None
        link = h2 if h2.name == "a" else h2.find("a")
        if link and link.get("href"):
            website = urljoin(base_url, link["href"])

        # Get description from p tag in header > div
        description = None
        header = article.find("header")
        if header:
            div = header.find("div")
            if div:
                p = div.find("p")
                if p:
                    description = p.get_text(strip=True)
                    if description and len(description) > 500:
                        description = description[:500]

        # Get KPIs: acquisition date, HQ country, employees
        kpi_div = article.select_one("div.kpi-portfolio")
        hq = None
        if kpi_div:
            # HQ country
            country_div = kpi_div.select_one("div.country")
            if country_div:
                ps = country_div.find_all("p")
                for p in ps:
                    if not p.find("strong"):
                        hq = p.get_text(strip=True)
                        break

        companies.append({
            "name": name,
            "sector": None,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": 0.85,
        })

    return companies


EXTRACTORS = {
    "portfolio": extract_portfolio,
}
