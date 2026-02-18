"""Site-specific extractors for www.furstenbergsgr.eu (Fürstenberg SGR).

Banca Ifis Group SGR. No public portfolio page.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.furstenbergsgr.eu"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
