"""Site-specific extractors for ranciliocube.com (Rancilio Cube Sicaf).

VC fund. Blog-only format, no structured portfolio page.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "ranciliocube.com"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
