"""Extractor regression tests for bot-protected/blocked fund domains."""

import json

from fundradar_worker.differ import extract_news_items
from fundradar_worker.strategies.extractors import (
    algebris,
    capital_dynamics_sgr,
    carlyle,
    oxy_capital,
    sagitta_sgr,
)


def test_blocked_funds_have_monitor_urls_configured():
    """Previously blocked funds should not have empty URL declarations."""
    assert algebris.URLS["portfolio"] is None
    assert algebris.URLS["news"]
    assert any("news.google.com/rss/search" in url for url in algebris.URLS["news"])
    assert capital_dynamics_sgr.URLS["news"]
    assert any("news.google.com/rss/search" in url for url in capital_dynamics_sgr.URLS["news"])
    assert carlyle.URLS["portfolio"]
    assert carlyle.URLS["news"]
    assert oxy_capital.URLS["news"]
    assert sagitta_sgr.URLS["news"]


def test_algebris_news_detail_fallback():
    html = """
    <html>
      <head>
        <meta property="og:title" content="Algebris Green Transition Fund acquires Esapro" />
      </head>
      <body>
        <time datetime="2026-01-17T10:30:00Z"></time>
        <p>Acquisition expands transition-enabler capabilities.</p>
      </body>
    </html>
    """
    items = algebris.extract_news(
        html,
        "https://www.algebris.com/it/press-release/algebris-green-transition-fund-acquires-100-of-esapro-italian-energy-transition-enabler/",
    )
    assert len(items) == 1
    assert items[0]["title"] == "Algebris Green Transition Fund acquires Esapro"
    assert items[0]["date"] == "2026-01-17"


def test_capdyn_news_detail_fallback():
    html = """
    <html>
      <body>
        <h1>Capital Dynamics ends 2024 as one of Italy's leaders in renewable energy asset construction</h1>
        <time datetime="2025-01-30T09:00:00Z"></time>
        <article><p>Capital Dynamics announced completion of new plants.</p></article>
      </body>
    </html>
    """
    items = capital_dynamics_sgr.extract_news(
        html,
        "https://www.capdyn.com/news-research-events/press-releases/capital-dynamics-ends-2024-as-one-of-italys-leaders-in-renewable-energy-asset-construction/",
    )
    assert len(items) == 1
    assert "Capital Dynamics ends 2024" in items[0]["title"]
    assert items[0]["date"] == "2025-01-30"


def test_carlyle_portfolio_detail_fallback():
    html = "<html><body><h1>Golden Goose Deluxe Brand</h1></body></html>"
    items = carlyle.extract_portfolio(
        html,
        "https://www.carlyle.com/our-business/portfolio-of-investments/golden-goose-deluxe-brand",
    )
    assert len(items) == 1
    assert items[0]["name"] == "Golden Goose Deluxe Brand"
    assert items[0]["status"] == "current"


def test_oxy_news_parses_wp_json_payload():
    payload = json.dumps(
        [
            {
                "title": {"rendered": "Oxy Capital announces new exit"},
                "date": "2026-02-10T08:30:00",
                "link": "https://oxycapital.com/oxy-capital-announces-new-exit/",
                "excerpt": {"rendered": "<p>Exit completed with strategic buyer.</p>"},
            },
            {
                "title": {"rendered": "Portfolio company expands in Europe"},
                "date": "2026-02-09T09:15:00",
                "link": "https://oxycapital.com/portfolio-company-expands-in-europe/",
                "excerpt": {"rendered": "<p>Company opened two new offices.</p>"},
            },
        ]
    )
    items = oxy_capital.extract_news(
        payload,
        "https://oxycapital.com/wp-json/wp/v2/posts?per_page=20&_fields=id,title,date,link,excerpt",
    )
    assert len(items) == 2
    assert items[0]["date"] == "2026-02-10"
    assert items[0]["url"].startswith("https://oxycapital.com/")


def test_sagitta_newsroom_list_parsing():
    html = """
    <html>
      <body>
        <article>
          <h3><a href="/en/newsroom/new-investment/">Sagitta completes new acquisition in Milan</a></h3>
          <time datetime="2026-02-10T08:00:00Z"></time>
        </article>
        <article>
          <h3><a href="/en/newsroom/debt-platform-update/">Debt platform expands operations in Italy</a></h3>
          <p>Published 11/02/2026</p>
        </article>
      </body>
    </html>
    """
    items = sagitta_sgr.extract_news(html, "https://www.sagittasgr.it/en/newsroom/")
    assert len(items) == 2
    assert any(i["url"] == "https://www.sagittasgr.it/en/newsroom/new-investment/" for i in items)
    assert any(i["date"] == "2026-02-10" for i in items)
    assert any(i["date"] == "2026-02-11" for i in items)


def test_generic_news_extractor_parses_rss_xml():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Feed</title>
        <item>
          <title>Capital Dynamics closes new clean energy transaction</title>
          <link>https://news.google.com/rss/articles/example-1</link>
          <pubDate>Thu, 19 Feb 2026 10:00:00 GMT</pubDate>
        </item>
        <item>
          <title>Algebris announces new platform investment</title>
          <link>https://news.google.com/rss/articles/example-2</link>
          <pubDate>Wed, 18 Feb 2026 08:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
    items = extract_news_items(rss, "https://news.google.com/rss/search?q=test")
    assert len(items) == 2
    assert items[0]["title"] == "Capital Dynamics closes new clean energy transaction"
    assert items[0]["date"] == "2026-02-19"
