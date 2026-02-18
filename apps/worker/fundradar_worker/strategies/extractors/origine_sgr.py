"""Site-specific extractors for www.originesgr.com (Origine SGR).

Coming soon page as of Feb 2026.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.originesgr.com"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
