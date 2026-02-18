#!/usr/bin/env python3
"""
Rebuild canonical Gemini audit/progress artifacts from canonical JSONL.

Thin wrapper around recover-gemini-fund-asset-audit-from-logs.py with
safe default paths wired to canonical locations.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVED = REPO_ROOT / "data" / "derived"
DEFAULT_CANONICAL_JSONL = DERIVED / "gemini_fund_asset_logs" / "fund_checks_deduplicated.jsonl"
DEFAULT_OUTPUT = DERIVED / "gemini_fund_asset_audit.json"
DEFAULT_PROGRESS = DERIVED / "gemini_fund_asset_audit_progress.json"
DEFAULT_REPORT = DERIVED / "gemini_fund_asset_audit_recovery_report.json"
DEFAULT_ZERO_ITALY_VERIFIED = DERIVED / "gemini_fund_asset_zero_italy_verified.json"
RECOVER_SCRIPT = REPO_ROOT / "scripts" / "recover-gemini-fund-asset-audit-from-logs.py"


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild canonical Gemini audit/progress from canonical JSONL.")
    parser.add_argument(
        "--canonical-jsonl-path",
        type=str,
        default=str(DEFAULT_CANONICAL_JSONL.relative_to(REPO_ROOT)),
        help="Canonical deduplicated JSONL source-of-truth path",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=str(DEFAULT_OUTPUT.relative_to(REPO_ROOT)),
        help="Canonical audit output JSON path",
    )
    parser.add_argument(
        "--progress-path",
        type=str,
        default=str(DEFAULT_PROGRESS.relative_to(REPO_ROOT)),
        help="Canonical audit progress JSON path",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=str(DEFAULT_REPORT.relative_to(REPO_ROOT)),
        help="Recovery report JSON path",
    )
    parser.add_argument(
        "--zero-italy-verified-path",
        type=str,
        default=str(DEFAULT_ZERO_ITALY_VERIFIED.relative_to(REPO_ROOT)),
        help="Whitelist path for verified zero-Italy slugs",
    )
    parser.add_argument(
        "--include-all-db-funds",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include funds without existing portfolio rows in DB queue",
    )
    parser.add_argument(
        "--allow-non-db-slugs",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Allow non-db slugs during recovery (default false)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run recovery parse/report only")
    args = parser.parse_args()

    canonical_jsonl = resolve_repo_relative_path(args.canonical_jsonl_path)
    if not canonical_jsonl.exists():
        print(f"Error: canonical JSONL not found: {canonical_jsonl}")
        return 2

    cmd = [
        sys.executable,
        str(RECOVER_SCRIPT),
        "--input-jsonl",
        str(canonical_jsonl),
        "--dedup-jsonl-path",
        str(canonical_jsonl),
        "--output-path",
        str(resolve_repo_relative_path(args.output_path)),
        "--progress-path",
        str(resolve_repo_relative_path(args.progress_path)),
        "--report-path",
        str(resolve_repo_relative_path(args.report_path)),
        "--zero-italy-verified-path",
        str(resolve_repo_relative_path(args.zero_italy_verified_path)),
    ]
    if args.include_all_db_funds:
        cmd.append("--include-all-db-funds")
    if args.allow_non_db_slugs:
        cmd.append("--allow-non-db-slugs")
    if args.dry_run:
        cmd.append("--dry-run")

    print("Running:")
    print(" ".join(cmd))
    result = subprocess.run(cmd)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
