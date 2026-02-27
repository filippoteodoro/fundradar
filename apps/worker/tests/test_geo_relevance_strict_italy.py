"""Geo relevance regression tests for strict Italy main-feed policy."""

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from filter_signals import _is_geo_relevant_signal  # noqa: E402


def _signal(
    title: str,
    *,
    signal_type: str = "deal_announced",
    italy_relevant: bool | None = None,
    relevance_score: float | int | None = None,
    relevance_reasons: list[str] | None = None,
    extracted_locations: list[str] | None = None,
) -> dict:
    return {
        "title": title,
        "what_changed": "",
        "diff_summary": "",
        "signal_type": signal_type,
        "italy_relevant": italy_relevant,
        "relevance_score": relevance_score,
        "relevance_reasons": relevance_reasons or [],
        "extracted_entities": {"locations": extracted_locations or []},
    }


def test_mixed_global_europe_only_is_not_kept():
    signal = _signal(
        "PATRIZIA invests in Southern Germany housing assets",
        italy_relevant=True,
        relevance_score=0,
        relevance_reasons=[],
    )
    fund = {"name": "PATRIZIA", "geographies": ["Europe", "North America", "Asia-Pacific"]}
    assert _is_geo_relevant_signal(signal, "mixed_or_global", fund) is False


def test_mixed_global_with_explicit_italy_text_is_kept():
    signal = _signal("Silver Lake invests in Italian software company based in Milan")
    fund = {"name": "Silver Lake", "geographies": ["North America", "Europe", "Asia-Pacific"]}
    assert _is_geo_relevant_signal(signal, "mixed_or_global", fund) is True


def test_europe_wide_without_italy_geo_requires_explicit_italy():
    signal = _signal("Pan-European expansion into France and Germany")
    fund = {"name": "Oakley Capital", "geographies": ["Europe"]}
    assert _is_geo_relevant_signal(signal, "europe_wide", fund) is False


def test_europe_wide_with_italy_geo_still_requires_explicit_italy():
    signal = _signal("Acquisition of French business unit in Lyon")
    fund = {"name": "Investindustrial", "geographies": ["Italy", "Europe"]}
    assert _is_geo_relevant_signal(signal, "europe_wide", fund) is False


def test_italy_focused_core_type_still_passes_without_explicit_italy():
    signal = _signal("Wise Equity announces a new investment", signal_type="deal_announced")
    fund = {"name": "Wise Equity SGR", "geographies": ["Italy"]}
    assert _is_geo_relevant_signal(signal, "italy_focused", fund) is True


def test_italy_focused_non_core_with_non_eu_geo_is_rejected():
    signal = _signal("Opening a new office in the United States", signal_type="people_move")
    fund = {"name": "Wise Equity SGR", "geographies": ["Italy"]}
    assert _is_geo_relevant_signal(signal, "italy_focused", fund) is False


def test_explicit_italy_reasons_keep_signal():
    signal = _signal(
        "Strategic acquisition announced",
        relevance_reasons=["Italian company"],
        relevance_score=0.7,
    )
    fund = {"name": "Silver Lake", "geographies": ["North America", "Europe", "Asia-Pacific"]}
    assert _is_geo_relevant_signal(signal, "mixed_or_global", fund) is True


def test_explicit_italy_entity_location_keeps_signal():
    signal = _signal(
        "Strategic acquisition announced",
        extracted_locations=["Milan"],
    )
    fund = {"name": "Silver Lake", "geographies": ["North America", "Europe", "Asia-Pacific"]}
    assert _is_geo_relevant_signal(signal, "mixed_or_global", fund) is True
