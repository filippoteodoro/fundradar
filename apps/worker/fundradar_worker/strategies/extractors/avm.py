"""Site-specific extractors for www.avmgestioni.com (AVM Gestioni SGR).

Site was down as of Feb 2026.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.avmgestioni.com"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
