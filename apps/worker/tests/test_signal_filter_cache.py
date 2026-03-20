"""Regression tests for filter cache helpers in filter_signals.py."""

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from filter_signals import (  # noqa: E402
    _compute_filter_cache_context,
    _exact_dedup_signals,
    _raw_signal_cache_fingerprint,
    _signal_fund_url_key,
)


def test_raw_signal_cache_fingerprint_changes_with_signal_content():
    signal = {
        "id": "sig-1",
        "fund_slug": "blackstone",
        "source_url": "https://example.com/article",
        "title": "Blackstone approves plan",
        "what_changed": "Financial plan approved",
        "observed_at": "2026-03-20T10:00:00+00:00",
    }
    original = _raw_signal_cache_fingerprint(signal, "blackstone")
    changed = _raw_signal_cache_fingerprint({**signal, "title": "Blackstone approves revised plan"}, "blackstone")
    assert original != changed


def test_raw_signal_cache_fingerprint_changes_with_filter_relevant_upstream_fields():
    signal = {
        "id": "sig-2",
        "fund_slug": "blackstone",
        "source_url": "https://example.com/article",
        "title": "Blackstone approves plan",
        "title_original": "Blackstone approva il piano",
        "what_changed": "Financial plan approved",
        "what_changed_original": "Piano finanziario approvato",
        "relevance_score": 0,
        "relevance_reasons": [],
        "observed_at": "2026-03-20T10:00:00+00:00",
    }
    original = _raw_signal_cache_fingerprint(signal, "blackstone")
    changed_original = _raw_signal_cache_fingerprint({**signal, "title_original": "Blackstone approva il nuovo piano"}, "blackstone")
    changed_relevance = _raw_signal_cache_fingerprint({**signal, "relevance_reasons": ["italy_keyword"]}, "blackstone")
    assert original != changed_original
    assert original != changed_relevance


def test_filter_cache_context_changes_when_dependency_content_changes(tmp_path):
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.json"
    file_a.write_text("print('a')\n", encoding="utf-8")
    file_b.write_text('{"x":1}\n', encoding="utf-8")
    original = _compute_filter_cache_context((file_a, file_b))
    file_b.write_text('{"x":2}\n', encoding="utf-8")
    changed = _compute_filter_cache_context((file_a, file_b))
    assert original != changed


def test_signal_fund_url_key_ignores_listing_pages():
    listing_signal = {
        "fund_slug": "kkr",
        "source_url": "https://www.kkr.com/insights",
    }
    article_signal = {
        "fund_slug": "kkr",
        "source_url": "https://www.kkr.com/newsroom/article-123",
    }
    assert _signal_fund_url_key(listing_signal) is None
    assert _signal_fund_url_key(article_signal) == "kkr::https://www.kkr.com/newsroom/article-123"


def test_exact_dedup_signals_prefers_newest_duplicate():
    older = {
        "id": "sig-old",
        "fund_slug": "hld",
        "title": "Kiloutou strengthens its foothold in Italy",
        "source_url": "https://example.com/hld/older",
        "observed_at": "2026-03-16T09:00:00+00:00",
        "quality_score": 88,
        "_raw_fingerprint": "fp-old",
    }
    newer = {
        "id": "sig-new",
        "fund_slug": "hld",
        "title": "Kiloutou strengthens its foothold in Italy",
        "source_url": "https://example.com/hld/newer",
        "observed_at": "2026-03-16T10:00:00+00:00",
        "quality_score": 91,
        "_raw_fingerprint": "fp-new",
    }
    deduped, removed_duplicates, resolved_duplicate_ids = _exact_dedup_signals([older, newer])
    assert removed_duplicates == 1
    assert resolved_duplicate_ids == 0
    assert len(deduped) == 1
    assert deduped[0]["id"] == "sig-new"
    assert deduped[0]["_raw_fingerprint"] == "fp-new"
