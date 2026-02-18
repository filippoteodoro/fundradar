#!/usr/bin/env python3
"""
Validate canonical Gemini audit state.

Checks:
- Canonical JSONL exists and is non-empty
- Canonical JSONL rows are parseable JSON objects
- Canonical audit/progress files exist
- Canonical audit/progress can be deterministically regenerated from canonical JSONL
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVED = REPO_ROOT / "data" / "derived"

DEFAULT_CANONICAL_JSONL = DERIVED / "gemini_fund_asset_logs" / "fund_checks_deduplicated.jsonl"
DEFAULT_AUDIT = DERIVED / "gemini_fund_asset_audit.json"
DEFAULT_PROGRESS = DERIVED / "gemini_fund_asset_audit_progress.json"
DEFAULT_REPORT = DERIVED / "gemini_fund_asset_audit_recovery_report.json"
DEFAULT_ZERO_ITALY_VERIFIED = DERIVED / "gemini_fund_asset_zero_italy_verified.json"
RECOVER_SCRIPT = REPO_ROOT / "scripts" / "recover-gemini-fund-asset-audit-from-logs.py"

VOLATILE_KEYS = {
    "generated_at",
    "run_recovered_at",
    "updated_at",
    "started_at",
}


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return data


def normalize_for_compare(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in VOLATILE_KEYS:
                continue
            out[key] = normalize_for_compare(value[key])
        return out
    if isinstance(value, list):
        # Preserve list order by default. For fund lists, normalize deterministically by slug.
        if value and all(isinstance(x, dict) and isinstance(x.get("slug"), str) for x in value):
            sorted_list = sorted(value, key=lambda x: str(x.get("slug")))
            return [normalize_for_compare(x) for x in sorted_list]
        return [normalize_for_compare(x) for x in value]
    return value


def summarize_fund_drift(current: dict[str, Any], regenerated: dict[str, Any]) -> dict[str, Any]:
    current_funds = current.get("funds") if isinstance(current.get("funds"), list) else []
    regen_funds = regenerated.get("funds") if isinstance(regenerated.get("funds"), list) else []

    cur_map = {
        f.get("slug"): f
        for f in current_funds
        if isinstance(f, dict) and isinstance(f.get("slug"), str)
    }
    reg_map = {
        f.get("slug"): f
        for f in regen_funds
        if isinstance(f, dict) and isinstance(f.get("slug"), str)
    }
    cur_slugs = set(cur_map.keys())
    reg_slugs = set(reg_map.keys())

    changed_shared: list[str] = []
    for slug in sorted(cur_slugs & reg_slugs):
        if normalize_for_compare(cur_map[slug]) != normalize_for_compare(reg_map[slug]):
            changed_shared.append(slug)

    return {
        "current_fund_count": len(cur_slugs),
        "regenerated_fund_count": len(reg_slugs),
        "missing_in_regenerated": sorted(cur_slugs - reg_slugs),
        "extra_in_regenerated": sorted(reg_slugs - cur_slugs),
        "changed_shared_count": len(changed_shared),
        "changed_shared_preview": changed_shared[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical Gemini audit state.")
    parser.add_argument(
        "--canonical-jsonl-path",
        type=str,
        default=str(DEFAULT_CANONICAL_JSONL.relative_to(REPO_ROOT)),
        help="Canonical deduplicated JSONL source-of-truth path",
    )
    parser.add_argument(
        "--audit-path",
        type=str,
        default=str(DEFAULT_AUDIT.relative_to(REPO_ROOT)),
        help="Current canonical audit JSON path",
    )
    parser.add_argument(
        "--progress-path",
        type=str,
        default=str(DEFAULT_PROGRESS.relative_to(REPO_ROOT)),
        help="Current canonical progress JSON path",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=str(DEFAULT_REPORT.relative_to(REPO_ROOT)),
        help="Current canonical recovery report JSON path",
    )
    parser.add_argument(
        "--zero-italy-verified-path",
        type=str,
        default=str(DEFAULT_ZERO_ITALY_VERIFIED.relative_to(REPO_ROOT)),
        help="Whitelist path for verified zero-Italy slugs",
    )
    parser.add_argument(
        "--allow-non-db-slugs",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Forwarded to recovery check (default false)",
    )
    args = parser.parse_args()

    canonical_jsonl_path = resolve_repo_relative_path(args.canonical_jsonl_path)
    audit_path = resolve_repo_relative_path(args.audit_path)
    progress_path = resolve_repo_relative_path(args.progress_path)
    report_path = resolve_repo_relative_path(args.report_path)
    zero_italy_verified_path = resolve_repo_relative_path(args.zero_italy_verified_path)

    failures: list[str] = []
    report: dict[str, Any] = {
        "paths": {
            "canonical_jsonl": str(canonical_jsonl_path),
            "audit": str(audit_path),
            "progress": str(progress_path),
            "report": str(report_path),
            "zero_italy_verified": str(zero_italy_verified_path),
        },
        "checks": {},
        "status": "ok",
    }

    # Check canonical JSONL existence + parseability
    if not canonical_jsonl_path.exists():
        failures.append("canonical_jsonl_missing")
        report["checks"]["canonical_jsonl"] = {"exists": False}
    else:
        rows_total = 0
        parse_errors = 0
        non_object_rows = 0
        with open(canonical_jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                rows_total += 1
                try:
                    row = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                if not isinstance(row, dict):
                    non_object_rows += 1

        report["checks"]["canonical_jsonl"] = {
            "exists": True,
            "rows_total": rows_total,
            "parse_errors": parse_errors,
            "non_object_rows": non_object_rows,
        }
        if rows_total == 0:
            failures.append("canonical_jsonl_empty")
        if parse_errors > 0:
            failures.append("canonical_jsonl_parse_errors")
        if non_object_rows > 0:
            failures.append("canonical_jsonl_non_object_rows")

    # Check current derived artifacts existence
    report["checks"]["derived_files"] = {
        "audit_exists": audit_path.exists(),
        "progress_exists": progress_path.exists(),
        "report_exists": report_path.exists(),
    }
    if not audit_path.exists():
        failures.append("audit_missing")
    if not progress_path.exists():
        failures.append("progress_missing")

    # Rebuild into temp and compare for drift if prerequisites exist.
    if not failures:
        with tempfile.TemporaryDirectory(prefix="gemini_state_validate_") as tmpdir_raw:
            tmpdir = Path(tmpdir_raw)
            regen_dedup = tmpdir / "fund_checks_deduplicated.jsonl"
            regen_audit = tmpdir / "gemini_fund_asset_audit.json"
            regen_progress = tmpdir / "gemini_fund_asset_audit_progress.json"
            regen_report = tmpdir / "gemini_fund_asset_audit_recovery_report.json"

            cmd = [
                sys.executable,
                str(RECOVER_SCRIPT),
                "--include-all-db-funds",
                "--input-jsonl",
                str(canonical_jsonl_path),
                "--dedup-jsonl-path",
                str(regen_dedup),
                "--output-path",
                str(regen_audit),
                "--progress-path",
                str(regen_progress),
                "--report-path",
                str(regen_report),
                "--zero-italy-verified-path",
                str(zero_italy_verified_path),
            ]
            if args.allow_non_db_slugs:
                cmd.append("--allow-non-db-slugs")

            run = subprocess.run(cmd, capture_output=True, text=True)
            report["checks"]["rebuild_command"] = {
                "return_code": run.returncode,
                "stdout_tail": run.stdout[-1200:],
                "stderr_tail": run.stderr[-1200:],
            }
            if run.returncode != 0:
                failures.append("rebuild_failed")
            else:
                current_audit = load_json(audit_path)
                current_progress = load_json(progress_path)
                regenerated_audit = load_json(regen_audit)
                regenerated_progress = load_json(regen_progress)

                audit_equal = normalize_for_compare(current_audit) == normalize_for_compare(regenerated_audit)
                progress_equal = normalize_for_compare(current_progress) == normalize_for_compare(regenerated_progress)
                report["checks"]["drift"] = {
                    "audit_equal": audit_equal,
                    "progress_equal": progress_equal,
                    "fund_drift_summary": summarize_fund_drift(current_audit, regenerated_audit),
                }
                if not audit_equal:
                    failures.append("audit_drift")
                if not progress_equal:
                    failures.append("progress_drift")

    report["failures"] = failures
    if failures:
        report["status"] = "failed"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
