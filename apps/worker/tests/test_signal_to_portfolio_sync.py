"""Regression tests for signal_to_portfolio reconciliation behavior."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from signal_to_portfolio import (  # noqa: E402
    _requires_reconciliation,
    process_fund_signals,
)


def test_exit_updates_when_status_is_none():
    existing = [{"name": "Witors", "status": None, "curation_locked": False}]
    signals = [{
        "id": "sig-1",
        "target_companies": [
            {"name": "Witor's", "is_direct_investment": True, "action": "exit"}
        ],
        "source_url": "https://example.com/news",
        "published_at": "2026-01-01T00:00:00Z",
    }]
    stats, processed = process_fund_signals(
        fund_slug="dummy-fund",
        fund_name="Dummy Fund",
        signals=signals,
        existing_entries=existing,
        fund_domain=None,
        dry_run=False,
    )
    assert stats["exits_updated"] == 1
    assert existing[0]["status"] == "exited"
    assert processed == ["sig-1"]


def test_invalid_target_company_name_is_skipped():
    existing: list[dict] = []
    signals = [{
        "id": "sig-2",
        "target_companies": [
            {"name": "Insights", "is_direct_investment": True, "action": "investment"}
        ],
        "source_url": "https://example.com/news",
        "published_at": "2026-01-01T00:00:00Z",
    }]
    stats, _ = process_fund_signals(
        fund_slug="dummy-fund",
        fund_name="Dummy Fund",
        signals=signals,
        existing_entries=existing,
        fund_domain=None,
        dry_run=False,
    )
    assert stats["added"] == 0
    assert stats["skipped_invalid_name"] == 1


def test_requires_reconciliation_for_missing_investment():
    existing: list[dict] = []
    signal = {
        "id": "sig-3",
        "target_companies": [
            {"name": "Travelsoft", "is_direct_investment": True, "action": "investment"}
        ],
    }
    assert _requires_reconciliation(signal, "dummy-fund", existing) is True


def test_requires_reconciliation_for_unapplied_exit():
    existing = [{"name": "Nexi", "status": "current"}]
    signal = {
        "id": "sig-4",
        "target_companies": [
            {"name": "Nexi", "is_direct_investment": True, "action": "exit"}
        ],
    }
    assert _requires_reconciliation(signal, "dummy-fund", existing) is True


def test_no_reconciliation_when_exit_already_applied():
    existing = [{"name": "Nexi", "status": "exited"}]
    signal = {
        "id": "sig-5",
        "target_companies": [
            {"name": "Nexi", "is_direct_investment": True, "action": "exit"}
        ],
    }
    assert _requires_reconciliation(signal, "dummy-fund", existing) is False


def test_exit_updates_all_matching_variants():
    existing = [
        {"name": "Nexi", "status": "current", "curation_locked": False},
        {"name": "Nexi S.p.A.", "status": None, "curation_locked": False},
    ]
    signals = [{
        "id": "sig-6",
        "target_companies": [
            {"name": "Nexi", "is_direct_investment": True, "action": "exit"}
        ],
        "source_url": "https://example.com/news",
        "published_at": "2026-01-01T00:00:00Z",
    }]
    stats, _ = process_fund_signals(
        fund_slug="dummy-fund",
        fund_name="Dummy Fund",
        signals=signals,
        existing_entries=existing,
        fund_domain=None,
        dry_run=False,
    )
    assert stats["exits_updated"] == 2
    assert all(e["status"] == "exited" for e in existing)
