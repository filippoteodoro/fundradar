"""Site-specific extractors for www.polis-sgr.com (Polis SGR).

Real estate and renewable energy focus. No PE portfolio.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.polis-sgr.com"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
