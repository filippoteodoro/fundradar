#!/usr/bin/env python3
"""
Shared completion rules for Gemini fund-asset audit outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _as_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return 0
        try:
            if "." in raw:
                return max(int(float(raw)), 0)
            return max(int(raw), 0)
        except ValueError:
            return 0
    return 0


def load_verified_zero_italy_slugs(path: Path) -> set[str]:
    if not path.exists():
        return set()

    # Support either JSON list/object or a plain newline-separated text file.
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}

    candidates: list[str] = []
    if isinstance(parsed, list):
        candidates = [str(x).strip() for x in parsed if isinstance(x, str)]
    elif isinstance(parsed, dict):
        for key in ("verified_slugs", "slugs", "funds"):
            value = parsed.get(key)
            if isinstance(value, list):
                candidates = [str(x).strip() for x in value if isinstance(x, str)]
                break

    return {slug for slug in candidates if slug}


def is_fund_result_complete(
    fund: dict[str, Any],
    *,
    verified_zero_italy_slugs: set[str] | None = None,
) -> tuple[bool, list[str]]:
    verified = verified_zero_italy_slugs or set()
    reasons: list[str] = []

    status = str(fund.get("status") or "").strip().lower()
    if status != "ok":
        reasons.append("status_not_ok")

    unresolved = _as_non_negative_int(fund.get("unresolved_entries_after_split"))
    if unresolved > 0:
        reasons.append("unresolved_entries")

    diagnostics = fund.get("call_diagnostics")
    if not isinstance(diagnostics, list) or not diagnostics:
        reasons.append("missing_call_diagnostics")
    else:
        has_missing_assets_success = False
        has_call_error = False
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            if item.get("error"):
                has_call_error = True
            if item.get("missing_assets_call") and not item.get("error"):
                has_missing_assets_success = True
        if has_call_error:
            reasons.append("call_errors")
        if not has_missing_assets_success:
            reasons.append("missing_assets_call_missing")

    italian_count = _as_non_negative_int(fund.get("italian_portfolio_count"))
    audited_count = _as_non_negative_int(fund.get("audited_portfolio_count"))
    missing_assets = fund.get("missing_assets")
    missing_count = len(missing_assets) if isinstance(missing_assets, list) else 0

    if italian_count > 0 and audited_count == 0:
        reasons.append("no_audited_entries")

    slug = str(fund.get("slug") or "").strip()
    if italian_count == 0 and missing_count == 0 and slug not in verified:
        reasons.append("zero_italian_unverified")

    return len(reasons) == 0, reasons

