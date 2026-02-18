#!/usr/bin/env python3
"""
Triage Gemini fund-asset audit suggestions into:
- ready_for_apply
- needs_openai_double_check
- rejected

Default policy:
- missing asset confidence=high -> ready_for_apply
- missing asset confidence=medium/low -> needs_openai_double_check

Manual overrides can force a decision per fund+asset.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVED_DIR = REPO_ROOT / "data" / "derived"

DEFAULT_INPUT = DERIVED_DIR / "gemini_fund_asset_audit.json"
DEFAULT_OUTPUT = DERIVED_DIR / "gemini_fund_asset_triage.json"
DEFAULT_OVERRIDES = DERIVED_DIR / "gemini_fund_asset_manual_review.json"

VALID_DECISIONS = {"ready_for_apply", "needs_openai_double_check", "rejected"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def norm(s: str) -> str:
    return s.strip().lower()


def get_override_decision(
    *,
    overrides: dict[str, Any],
    fund_slug: str,
    asset_name: str,
) -> tuple[str | None, str]:
    funds = overrides.get("funds")
    if not isinstance(funds, dict):
        return None, ""

    fund_block = funds.get(fund_slug)
    if not isinstance(fund_block, dict):
        return None, ""

    assets_block = fund_block.get("missing_assets")
    if not isinstance(assets_block, dict):
        return None, ""

    exact = assets_block.get(asset_name)
    if isinstance(exact, dict):
        decision = str(exact.get("decision") or "").strip()
        note = str(exact.get("note") or "").strip()
        return decision if decision else None, note

    # case-insensitive fallback
    lookup = {norm(k): v for k, v in assets_block.items() if isinstance(k, str) and isinstance(v, dict)}
    match = lookup.get(norm(asset_name))
    if not match:
        return None, ""

    decision = str(match.get("decision") or "").strip()
    note = str(match.get("note") or "").strip()
    return decision if decision else None, note


def default_decision_for_missing_asset(asset: dict[str, Any]) -> str:
    confidence = str(asset.get("confidence") or "").strip().lower()
    if confidence == "high":
        return "ready_for_apply"
    return "needs_openai_double_check"


def triage_missing_assets(
    *,
    fund_slug: str,
    missing_assets: list[dict[str, Any]],
    overrides: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    ready: list[dict[str, Any]] = []
    openai_check: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for asset in missing_assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").strip()
        if not name:
            continue

        decision = default_decision_for_missing_asset(asset)
        note = ""

        override_decision, override_note = get_override_decision(
            overrides=overrides,
            fund_slug=fund_slug,
            asset_name=name,
        )
        if override_decision:
            decision = override_decision
            note = override_note

        if decision not in VALID_DECISIONS:
            decision = "needs_openai_double_check"
            if not note:
                note = "invalid manual decision; moved to openai double-check"

        item = dict(asset)
        item["triage_decision"] = decision
        if note:
            item["triage_note"] = note

        if decision == "ready_for_apply":
            ready.append(item)
        elif decision == "rejected":
            rejected.append(item)
        else:
            openai_check.append(item)

    return ready, openai_check, rejected


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage Gemini fund asset audit suggestions.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to gemini_fund_asset_audit.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output triage JSON path")
    parser.add_argument(
        "--overrides",
        default=str(DEFAULT_OVERRIDES),
        help="Optional manual override JSON path",
    )
    parser.add_argument(
        "--no-overrides",
        action="store_true",
        help="Ignore override file and only use confidence policy",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    overrides_path = Path(args.overrides)

    if not input_path.exists():
        raise FileNotFoundError(f"Missing input file: {input_path}")

    audit = load_json(input_path)
    funds = audit.get("funds")
    if not isinstance(funds, list):
        raise ValueError("Input audit JSON is missing a valid 'funds' array")

    overrides: dict[str, Any] = {}
    if not args.no_overrides and overrides_path.exists():
        overrides = load_json(overrides_path)

    triaged_funds: list[dict[str, Any]] = []

    total_ready = 0
    total_openai = 0
    total_rejected = 0

    for fund in funds:
        if not isinstance(fund, dict):
            continue
        slug = str(fund.get("slug") or "").strip()
        if not slug:
            continue
        missing_assets = fund.get("missing_assets")
        missing_assets = missing_assets if isinstance(missing_assets, list) else []

        ready, openai_check, rejected = triage_missing_assets(
            fund_slug=slug,
            missing_assets=missing_assets,
            overrides=overrides,
        )

        total_ready += len(ready)
        total_openai += len(openai_check)
        total_rejected += len(rejected)

        triaged_funds.append({
            "slug": slug,
            "name": fund.get("name"),
            "missing_assets_ready_for_apply": ready,
            "missing_assets_needs_openai_double_check": openai_check,
            "missing_assets_rejected": rejected,
        })

    result = {
        "generated_at": now_iso(),
        "input_file": str(input_path),
        "overrides_file": str(overrides_path) if overrides else None,
        "summary": {
            "fund_count": len(triaged_funds),
            "missing_assets_ready_for_apply": total_ready,
            "missing_assets_needs_openai_double_check": total_openai,
            "missing_assets_rejected": total_rejected,
        },
        "funds": triaged_funds,
    }

    save_json(output_path, result)
    print(f"Wrote {output_path}")
    print(
        "Summary: "
        f"ready={total_ready}, openai_check={total_openai}, rejected={total_rejected}, funds={len(triaged_funds)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

