"""Site-specific extractors for www.cooperarespa.it (Cooperare).

Site timeout. No portfolio page found.
"""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "www.cooperarespa.it"


# URL paths — verified against live site
URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}


EXTRACTORS = {}
