"""Site-specific extractors for privateequitypartners.com.

Private Equity Partners website.
Note: The website appears to be inactive or returns empty content.
No portfolio or team data is available.
"""
from bs4 import BeautifulSoup

DOMAIN = "www.privateequitypartners.com"



# URL paths for monitoring (auto-generated from fund_urls.json)
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """
    Extract portfolio companies.
    Note: Website returns empty content.
    """
    return []


def extract_team(html: str, base_url: str) -> list[dict]:
    """
    Extract team members.
    Note: Website returns empty content.
    """
    return []


EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
}
