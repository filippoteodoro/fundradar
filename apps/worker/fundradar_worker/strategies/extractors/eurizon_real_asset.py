"""Site-specific extractors for www.eurizoncapital.com (Eurizon Real Asset).

Multi-manager platform. No company-level portfolio.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.eurizoncapital.com"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
