"""Site-specific extractors for searchlightcap.com.

Searchlight's portfolio page is JS-heavy and exposes accessibility text that is
frequently misparsed as company names. Portfolio is maintained manually in
data/derived/portfolio_items.json.
"""

DOMAIN = "searchlightcap.com"

URLS = {
    "portfolio": None,
    "team": None,
    "news": None,
}

EXTRACTORS = {}
