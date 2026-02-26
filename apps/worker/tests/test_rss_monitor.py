import sys
import types

# rss_monitor imports feedparser at module import time; provide a lightweight stub
# so this unit test can run even when optional feed dependencies are absent.
if "feedparser" not in sys.modules:
    sys.modules["feedparser"] = types.SimpleNamespace(
        parse=lambda *_args, **_kwargs: types.SimpleNamespace(bozo=False, entries=[])
    )

from fundradar_worker.rss_monitor import articles_to_signals


def test_articles_to_signals_emits_related_fund_slugs_for_all_accepted_funds():
    classified = [
        {
            "title": "Joint investment in Italy",
            "link": "https://example.com/article-1",
            "published": "2026-02-20T00:00:00Z",
            "_fund_name_matched_slugs": ["fund-a"],
            "classified": {
                "fund_slugs": ["fund-c", "fund-a", "fund-b"],
                "_llm_confirmed_slugs": ["fund-b"],
                "signal_type": "deal_announced",
                "italy_relevant": True,
                "summary": "Fund A and Fund B co-invest in a Milan-based company.",
                "companies": ["ExampleCo"],
                "amount": "€10M",
            },
        }
    ]

    signals = articles_to_signals(
        classified=classified,
        feed={"name": "Example Feed", "tier": 1},
        state={"signal_counter": 0},
        funds_by_slug={
            "fund-a": {"name": "Fund A"},
            "fund-b": {"name": "Fund B"},
            "fund-c": {"name": "Fund C"},
        },
    )

    # fund-c is filtered out (portfolio-only match), fund-a and fund-b are kept.
    assert len(signals) == 2
    assert [s["fund_slug"] for s in signals] == ["fund-a", "fund-b"]
    assert signals[0]["related_fund_slugs"] == ["fund-a", "fund-b"]
    assert signals[1]["related_fund_slugs"] == ["fund-a", "fund-b"]


def test_articles_to_signals_skips_article_when_no_fund_survives_guard():
    classified = [
        {
            "title": "Portfolio company generic mention",
            "link": "https://example.com/article-2",
            "_fund_name_matched_slugs": [],
            "classified": {
                "fund_slugs": ["fund-x"],
                "_llm_confirmed_slugs": [],
                "summary": "No direct fund action.",
            },
        }
    ]

    signals = articles_to_signals(
        classified=classified,
        feed={"name": "Example Feed", "tier": 2},
        state={"signal_counter": 12},
        funds_by_slug={"fund-x": {"name": "Fund X"}},
    )

    assert signals == []


def test_articles_to_signals_drops_speculative_bidder_mentions():
    classified = [
        {
            "title": "Apax launches sale of GamaLife insurance activities",
            "description": (
                "Apax Partners put up for sale GamaLife. Generali, CVC, Blackstone and "
                "Brookfield among interested bidders."
            ),
            "link": "https://example.com/article-3",
            "published": "2026-02-20T00:00:00Z",
            "_fund_name_matched_slugs": ["apax-partners", "blackstone"],
            "classified": {
                "fund_slugs": ["apax-partners", "blackstone"],
                "_llm_confirmed_slugs": ["apax-partners", "blackstone"],
                "signal_type": "exit_announced",
                "italy_relevant": True,
                "summary": "Apax starts sale process; Blackstone listed among interested bidders.",
                "companies": ["GamaLife"],
                "amount": None,
            },
        }
    ]

    signals = articles_to_signals(
        classified=classified,
        feed={"name": "Example Feed", "tier": 1},
        state={"signal_counter": 0},
        funds_by_slug={
            "apax-partners": {"name": "Apax Partners"},
            "blackstone": {"name": "Blackstone"},
        },
    )

    assert len(signals) == 1
    assert signals[0]["fund_slug"] == "apax-partners"
    assert signals[0]["related_fund_slugs"] == ["apax-partners"]


def test_articles_to_signals_keeps_active_seller_but_drops_in_running_bidder():
    classified = [
        {
            "title": (
                "Mecaer (Fondo Italiano d'Investimento), sale process launched. "
                "Carlyle and PAI Partners in the running."
            ),
            "description": (
                "Fondo Italiano starts the sale process. Carlyle and PAI are reportedly "
                "vying to acquire the business."
            ),
            "link": "https://example.com/article-4",
            "published": "2026-02-20T00:00:00Z",
            "_fund_name_matched_slugs": [
                "carlyle",
                "fondo-italiano-d-investimento-sgr",
                "pai-partners",
            ],
            "classified": {
                "fund_slugs": [
                    "carlyle",
                    "fondo-italiano-d-investimento-sgr",
                    "pai-partners",
                ],
                "_llm_confirmed_slugs": [
                    "carlyle",
                    "fondo-italiano-d-investimento-sgr",
                    "pai-partners",
                ],
                "signal_type": "deal_announced",
                "italy_relevant": True,
                "summary": "Seller launched process; bidders are in the running.",
                "companies": ["Mecaer"],
                "amount": None,
            },
        }
    ]

    signals = articles_to_signals(
        classified=classified,
        feed={"name": "Example Feed", "tier": 1},
        state={"signal_counter": 0},
        funds_by_slug={
            "carlyle": {"name": "Carlyle"},
            "fondo-italiano-d-investimento-sgr": {"name": "Fondo Italiano d'Investimento SGR"},
            "pai-partners": {"name": "PAI Partners"},
        },
    )

    assert [s["fund_slug"] for s in signals] == ["fondo-italiano-d-investimento-sgr"]
    assert signals[0]["related_fund_slugs"] == ["fondo-italiano-d-investimento-sgr"]
