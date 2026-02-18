"""Site-specific extractors for www.entrustglobal.com (EnTrust Global).

ShieldPRO blocks all automated access.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.entrustglobal.com"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
