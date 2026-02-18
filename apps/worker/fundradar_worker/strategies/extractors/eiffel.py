"""Site-specific extractors for www.eiffel-ig.com (Eiffel Investment Group).

French investment group. No public company-level portfolio.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.eiffel-ig.com"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
