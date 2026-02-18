#!/usr/bin/env python3
"""
Reconcile Gemini fund-asset audit outputs after interrupted parallel runs.

What it does:
- merges master + shard outputs into canonical master output
- marks only strictly complete slugs as completed to avoid false "done" state
- preserves partial_failure info in a dedicated list
- writes a remaining slugs file (current db/portfolio minus already-run)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gemini_audit_completion import is_fund_result_complete, load_verified_zero_italy_slugs

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVED = REPO_ROOT / "data" / "derived"
DB_PATH = REPO_ROOT / "data" / "db.json"
PORTFOLIO_PATH = DERIVED / "portfolio_items.json"

DEFAULT_OUTPUT_FILES = [
    DERIVED / "gemini_fund_asset_audit.json",
    DERIVED / "gemini_fund_asset_audit.shard1.json",
    DERIVED / "gemini_fund_asset_audit.shard2.json",
]
DEFAULT_PROGRESS_FILES = [
    DERIVED / "gemini_fund_asset_audit_progress.json",
    DERIVED / "gemini_fund_asset_audit_progress.shard1.json",
    DERIVED / "gemini_fund_asset_audit_progress.shard2.json",
]

MASTER_OUTPUT = DERIVED / "gemini_fund_asset_audit.json"
MASTER_PROGRESS = DERIVED / "gemini_fund_asset_audit_progress.json"
REMAINING_SLUGS = DERIVED / "gemini_fund_asset_remaining_slugs.txt"
ZERO_ITALY_VERIFIED = DERIVED / "gemini_fund_asset_zero_italy_verified.json"

# Legacy slug compatibility redirect for historical shard/log inputs.
LEGACY_SLUG_REDIRECTS: dict[str, str] = {
    "banca-sella-holding": "sella-venture-partners",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def parse_csv_paths(raw: str) -> list[Path]:
    out: list[Path] = []
    for token in raw.split(","):
        t = token.strip()
        if not t:
            continue
        p = Path(t)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if p.exists():
            out.append(p)
    return out


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def sort_funds_by_aum_desc(funds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(f: dict[str, Any]) -> tuple[bool, float, str]:
        aum = f.get("aum_eur")
        has_no_aum = aum is None
        aum_num = float(aum) if isinstance(aum, (int, float)) else -1.0
        return (has_no_aum, -aum_num, (f.get("name") or f.get("slug") or "").lower())

    return sorted(funds, key=key)


def build_current_queue_slugs(db: dict[str, Any], portfolio: dict[str, Any]) -> list[str]:
    funds = db.get("funds") or []
    fund_portfolios = portfolio.get("fund_portfolios") or {}
    queue: list[dict[str, Any]] = []
    for fund in funds:
        slug = fund.get("slug")
        if not slug:
            continue
        entries = fund_portfolios.get(slug, [])
        if not isinstance(entries, list) or len(entries) == 0:
            continue
        queue.append(fund)
    return [f["slug"] for f in sort_funds_by_aum_desc(queue) if f.get("slug")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile Gemini fund-asset audit outputs.")
    parser.add_argument(
        "--output-files",
        type=str,
        default=",".join(str(p.relative_to(REPO_ROOT)) for p in DEFAULT_OUTPUT_FILES),
        help="Comma-separated output json files to merge",
    )
    parser.add_argument(
        "--progress-files",
        type=str,
        default=",".join(str(p.relative_to(REPO_ROOT)) for p in DEFAULT_PROGRESS_FILES),
        help="Comma-separated progress json files to read",
    )
    parser.add_argument(
        "--write-remaining-slugs",
        action="store_true",
        help="Write remaining slugs file for next run",
    )
    parser.add_argument(
        "--zero-italy-verified-path",
        type=str,
        default=str(ZERO_ITALY_VERIFIED.relative_to(REPO_ROOT)),
        help="Path to JSON/TXT whitelist for funds verified to have no Italy assets",
    )
    args = parser.parse_args()

    output_files = parse_csv_paths(args.output_files)
    progress_files = parse_csv_paths(args.progress_files)

    if not output_files:
        print("Error: no output files found")
        return 2

    db = load_json(DB_PATH)
    portfolio = load_json(PORTFOLIO_PATH)
    current_queue = build_current_queue_slugs(db, portfolio)
    current_queue_set = set(current_queue)
    verified_zero_italy_slugs = load_verified_zero_italy_slugs(
        resolve_repo_relative_path(args.zero_italy_verified_path)
    )

    # Merge funds by slug, prefer newest file mtime.
    by_slug: dict[str, dict[str, Any]] = {}
    source_mtime: dict[str, float] = {}
    legacy_redirected = 0

    for path in output_files:
        data = load_json(path)
        funds = data.get("funds")
        if not isinstance(funds, list):
            continue
        mtime = path.stat().st_mtime
        for fund in funds:
            if not isinstance(fund, dict):
                continue
            raw_slug = fund.get("slug")
            if not isinstance(raw_slug, str) or not raw_slug.strip():
                continue
            slug = LEGACY_SLUG_REDIRECTS.get(raw_slug, raw_slug)
            item = dict(fund)
            if slug != raw_slug:
                item["legacy_slug"] = raw_slug
                item["slug"] = slug
                legacy_redirected += 1
            if slug not in by_slug or mtime > source_mtime[slug]:
                by_slug[slug] = item
                source_mtime[slug] = mtime

    # Build ordered merged funds following current queue order, then extras.
    merged_funds: list[dict[str, Any]] = []
    for slug in current_queue:
        if slug in by_slug:
            merged_funds.append(by_slug[slug])
    extras = [slug for slug in by_slug if slug not in current_queue_set]
    extras.sort()
    for slug in extras:
        merged_funds.append(by_slug[slug])

    status_counts: dict[str, int] = {}
    completed_slugs: set[str] = set()
    incomplete_slugs: list[str] = []
    incomplete_reason_counts: dict[str, int] = {}
    unverified_zero_italy_slugs: list[str] = []
    partial_failure_slugs: list[str] = []

    total_issues = 0
    total_missing = 0
    api_calls = 0
    api_failures = 0

    for fund in merged_funds:
        status = str(fund.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        slug = fund.get("slug")
        if status == "partial_failure" and isinstance(slug, str):
            partial_failure_slugs.append(slug)

        is_complete, reasons = is_fund_result_complete(
            fund,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        if isinstance(slug, str):
            if is_complete:
                completed_slugs.add(slug)
            else:
                incomplete_slugs.append(slug)
        for reason in reasons:
            incomplete_reason_counts[reason] = incomplete_reason_counts.get(reason, 0) + 1
        if isinstance(slug, str) and "zero_italian_unverified" in reasons:
            unverified_zero_italy_slugs.append(slug)

        issues = fund.get("wrong_or_correction_issues")
        if isinstance(issues, list):
            total_issues += len(issues)
        missing = fund.get("missing_assets")
        if isinstance(missing, list):
            total_missing += len(missing)
        diagnostics = fund.get("call_diagnostics")
        if isinstance(diagnostics, list):
            api_calls += len(diagnostics)
            api_failures += sum(1 for d in diagnostics if isinstance(d, dict) and d.get("error"))

    # Aggregate failed maps from progress files but do not force reruns for slugs with results.
    failed_map: dict[str, Any] = {}
    last_slug = None
    for path in progress_files:
        p = load_json(path)
        failed = p.get("failed")
        if isinstance(failed, dict):
            for slug, err in failed.items():
                failed_map[str(slug)] = err
        if p.get("last_slug"):
            last_slug = p.get("last_slug")

    for slug in list(failed_map.keys()):
        if slug in completed_slugs:
            failed_map.pop(slug, None)

    remaining = [slug for slug in current_queue if slug not in completed_slugs]

    output = {
        "generated_at": now_iso(),
        "model": "gemini-3-flash-preview",
        "run_reconciled_at": now_iso(),
        "funds": merged_funds,
        "summary": {
            "funds_in_queue": len(current_queue),
            "funds_with_results": len([s for s in by_slug if s in current_queue_set]),
            "funds_completed_or_partial": len([s for s in completed_slugs if s in current_queue_set]),
            "funds_completed_strict": len([s for s in completed_slugs if s in current_queue_set]),
            "funds_remaining": len(remaining),
            "total_wrong_or_correction_issues": total_issues,
            "total_missing_assets": total_missing,
            "api_calls": api_calls,
            "api_failures": api_failures,
            "status_counts": status_counts,
            "partial_failure_slugs": sorted(set(partial_failure_slugs)),
            "incomplete_reason_counts": dict(sorted(incomplete_reason_counts.items())),
            "unverified_zero_italy_slugs": sorted(set(unverified_zero_italy_slugs)),
            "zero_italy_verified_slugs_count": len(verified_zero_italy_slugs),
            "legacy_redirects_applied": legacy_redirected,
            "updated_at": now_iso(),
        },
    }
    save_json_atomic(MASTER_OUTPUT, output)

    progress = {
        "started_at": now_iso(),
        "completed_slugs": sorted(completed_slugs),
        "failed": failed_map,
        "last_slug": last_slug,
        "updated_at": now_iso(),
        "partial_failure_slugs": sorted(set(partial_failure_slugs)),
        "incomplete_slugs": sorted(set(incomplete_slugs)),
        "incomplete_reason_counts": dict(sorted(incomplete_reason_counts.items())),
        "unverified_zero_italy_slugs": sorted(set(unverified_zero_italy_slugs)),
        "zero_italy_verified_slugs_count": len(verified_zero_italy_slugs),
        "remaining_slugs_count": len(remaining),
    }
    save_json_atomic(MASTER_PROGRESS, progress)

    if args.write_remaining_slugs:
        REMAINING_SLUGS.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        print(f"Wrote remaining slugs: {REMAINING_SLUGS} ({len(remaining)})")

    print(f"Merged funds in queue: {len([s for s in by_slug if s in current_queue_set])}/{len(current_queue)}")
    print(f"Completed (strict): {len([s for s in completed_slugs if s in current_queue_set])}")
    print(f"Remaining: {len(remaining)}")
    if remaining:
        print("Next slugs preview:", ", ".join(remaining[:10]))
    print(f"Master output updated: {MASTER_OUTPUT}")
    print(f"Master progress updated: {MASTER_PROGRESS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
