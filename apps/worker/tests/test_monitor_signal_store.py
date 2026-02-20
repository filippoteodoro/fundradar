"""SignalStore regression tests for NEWS duplicate upsert behavior."""

import json
from pathlib import Path

from fundradar_worker.monitor import SignalStore


def _base_signal(signal_id: str, what_changed: str, observed_at: str, *, page_category: str = "NEWS") -> dict:
    return {
        "id": signal_id,
        "fund_slug": "wise-equity-sgr",
        "signal_type": "deal_announced",
        "title": "Wise Equity entra nel capitale di Marullo per accompagnarne la crescita",
        "what_changed": what_changed,
        "source_url": "https://www.wisesgr.com/web/content/458/15-12-2025_Comunicato-Stampa_WISE-Equity_Marullo_v-ITA_DEF.pdf",
        "source_name": "Wise Equity SGR",
        "published_at": "2025-12-15",
        "observed_at": observed_at,
        "created_at": observed_at,
        "diff_summary": "New news item detected",
        "page_category": page_category,
        "page_type": page_category,
        "extracted_entities": {"companies": [], "people": [], "locations": []},
    }


def test_signal_store_replaces_news_duplicate_with_newer_variant(tmp_path: Path):
    store = SignalStore(tmp_path / "detected_signals.json")

    old_signal = _base_signal(
        "web-signal-old",
        "New announcement: Wise Equity entra nel capitale diMarulloper accompagnarne la crescita",
        "2026-02-20T09:00:00+00:00",
    )
    new_signal = _base_signal(
        "web-signal-new",
        "New announcement: Wise Equity entra nel capitale di Marullo per accompagnarne la crescita",
        "2026-02-20T09:30:00+00:00",
    )

    store.add(old_signal)
    store.add(new_signal)

    assert len(store.signals) == 1
    kept = store.signals[0]
    assert kept["id"] == "web-signal-new"
    assert " di Marullo per " in kept["what_changed"]


def test_signal_store_keeps_non_news_same_identity_signals(tmp_path: Path):
    store = SignalStore(tmp_path / "detected_signals.json")

    first = _base_signal(
        "team-signal-1",
        "New team member: Alice Example",
        "2026-02-20T09:00:00+00:00",
        page_category="TEAM",
    )
    second = _base_signal(
        "team-signal-2",
        "New team member: Bob Example",
        "2026-02-20T09:30:00+00:00",
        page_category="TEAM",
    )
    # Same title/source/published, but TEAM signals should not be merged by NEWS key.
    second["title"] = first["title"]
    second["source_url"] = first["source_url"]
    second["published_at"] = first["published_at"]

    store.add(first)
    store.add(second)

    assert len(store.signals) == 2


def test_signal_store_collapses_existing_news_duplicates_on_load(tmp_path: Path):
    store_path = tmp_path / "detected_signals.json"
    old_signal = _base_signal(
        "web-signal-old",
        "New announcement: Wise Equity entra nel capitale diMarulloper accompagnarne la crescita",
        "2026-02-20T09:00:00+00:00",
    )
    new_signal = _base_signal(
        "web-signal-new",
        "New announcement: Wise Equity entra nel capitale di Marullo per accompagnarne la crescita",
        "2026-02-20T09:30:00+00:00",
    )

    store_path.write_text(
        json.dumps({"signals": [old_signal, new_signal], "signal_count": 2}),
        encoding="utf-8",
    )

    store = SignalStore(store_path)
    assert len(store.signals) == 1
    assert store.signals[0]["id"] == "web-signal-new"

    store.flush()
    persisted = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(persisted["signals"]) == 1
    assert persisted["signal_count"] == 1
