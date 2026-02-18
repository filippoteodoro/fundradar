"""Site-specific extractors for www.yarpa.it (Yarpa Investimenti SGR).

Fund-of-funds model. No company-level portfolio.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.yarpa.it"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
