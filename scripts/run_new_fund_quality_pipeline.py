#!/usr/bin/env python3
"""Run the end-to-end quality workflow for newly added funds."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
ASSET_AUDIT_PATH = DERIVED / "gemini_fund_asset_audit.json"
REPORT_REL = Path("data/derived/new_fund_completion_report.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_repo_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return ROOT / path


def _parse_slugs(raw: str) -> list[str]:
    slugs = sorted({token.strip() for token in raw.split(",") if token.strip()})
    return slugs


def _auto_detect_new_slugs_from_db() -> list[str]:
    db_path = ROOT / "data" / "db.json"
    payload = json.loads(db_path.read_text(encoding="utf-8"))
    funds = payload.get("funds")
    if not isinstance(funds, list) or not funds:
        return []

    created_values = [str(f.get("created_at") or "") for f in funds if isinstance(f, dict)]
    if not created_values:
        return []
    mode_value, _ = Counter(created_values).most_common(1)[0]

    out = sorted(
        str(f.get("slug"))
        for f in funds
        if isinstance(f, dict)
        and f.get("slug")
        and str(f.get("created_at") or "") != mode_value
    )
    return [slug for slug in out if slug]


def _run_shell(command: str, dry_run: bool) -> tuple[int, str]:
    if dry_run:
        print(f"[dry-run] {command}")
        return 0, ""
    proc = subprocess.run(
        command,
        cwd=ROOT,
        shell=True,
        executable="/bin/zsh",
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode, proc.stderr


def _network_preflight(hosts: list[str]) -> list[str]:
    failed: list[str] = []
    for host in hosts:
        try:
            socket.getaddrinfo(host, 443)
        except Exception:
            failed.append(host)
    return failed


@dataclass
class StageResult:
    stage: str
    command: str
    status: str
    started_at: str
    finished_at: str
    exit_code: int
    note: str | None = None


def _run_stage(stage: str, command: str, dry_run: bool) -> StageResult:
    started = _now_iso()
    print(f"\n== Stage: {stage} ==")
    code, stderr = _run_shell(command, dry_run=dry_run)
    finished = _now_iso()
    return StageResult(
        stage=stage,
        command=command,
        status="passed" if code == 0 else "failed",
        started_at=started,
        finished_at=finished,
        exit_code=code,
        note=stderr[:500] if stderr else None,
    )


def _run_apply_missing_assets_stage(slugs: list[str], dry_run: bool) -> StageResult:
    stage = "apply_missing_assets"
    started = _now_iso()
    command = (
        "python3 scripts/apply-gemini-missing-assets.py "
        "--inputs <temp_filtered_audit.json> "
        "--apply --italy-only --min-confidence medium --no-require-canonical-jsonl"
    )
    print(f"\n== Stage: {stage} ==")

    if dry_run:
        print(f"[dry-run] {command}")
        finished = _now_iso()
        return StageResult(
            stage=stage,
            command=command,
            status="passed",
            started_at=started,
            finished_at=finished,
            exit_code=0,
        )

    if not ASSET_AUDIT_PATH.exists():
        finished = _now_iso()
        return StageResult(
            stage=stage,
            command=command,
            status="failed",
            started_at=started,
            finished_at=finished,
            exit_code=2,
            note=f"Missing audit file: {ASSET_AUDIT_PATH}",
        )

    payload = json.loads(ASSET_AUDIT_PATH.read_text(encoding="utf-8"))
    rows = payload.get("funds")
    if not isinstance(rows, list):
        finished = _now_iso()
        return StageResult(
            stage=stage,
            command=command,
            status="failed",
            started_at=started,
            finished_at=finished,
            exit_code=2,
            note="Invalid gemini_fund_asset_audit.json format (funds[] missing)",
        )

    selected = set(slugs)
    filtered_rows = [row for row in rows if isinstance(row, dict) and row.get("slug") in selected]
    if not filtered_rows:
        finished = _now_iso()
        return StageResult(
            stage=stage,
            command=command,
            status="failed",
            started_at=started,
            finished_at=finished,
            exit_code=2,
            note="No matching slugs found in gemini_fund_asset_audit.json",
        )

    filtered_payload = {
        "generated_at": payload.get("generated_at"),
        "model": payload.get("model"),
        "funds": filtered_rows,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        json.dump(filtered_payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")

    apply_command = (
        "python3 scripts/apply-gemini-missing-assets.py "
        f"--inputs {tmp_path} "
        "--apply --italy-only --min-confidence medium --no-require-canonical-jsonl"
    )
    try:
        code, stderr = _run_shell(apply_command, dry_run=False)
        finished = _now_iso()
        return StageResult(
            stage=stage,
            command=apply_command,
            status="passed" if code == 0 else "failed",
            started_at=started,
            finished_at=finished,
            exit_code=code,
            note=stderr[:500] if stderr else None,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the standard quality pipeline for new funds")
    parser.add_argument("--slugs", type=str, default="", help="Comma-separated fund slugs")
    parser.add_argument(
        "--auto-detect-new",
        action="store_true",
        help="Use created_at outlier detection from db.json when --slugs is omitted",
    )
    parser.add_argument(
        "--summary-path",
        type=str,
        default=str((DERIVED / "new_fund_quality_pipeline_summary.json").relative_to(ROOT)),
        help="Summary JSON output path",
    )
    parser.add_argument(
        "--force-extract",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass --force-extract to pnpm pipeline",
    )
    parser.add_argument(
        "--apply-missing-assets",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Apply Gemini missing-asset suggestions for provided slugs only",
    )
    parser.add_argument(
        "--apply-backfill",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply top-AUM historical backfill for selected slugs",
    )
    parser.add_argument("--backfill-top-n", type=int, default=25, help="Top-AUM target set size")
    parser.add_argument("--backfill-min-signals", type=int, default=2, help="Minimum required signals per top fund")
    parser.add_argument(
        "--stop-on-fail",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stop immediately on first failed stage",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    parser.add_argument(
        "--skip-network-preflight",
        action="store_true",
        help="Skip DNS preflight checks (not recommended)",
    )
    args = parser.parse_args()

    slugs = _parse_slugs(args.slugs)
    if not slugs and args.auto_detect_new:
        slugs = _auto_detect_new_slugs_from_db()
    if not slugs:
        print("Error: provide --slugs or use --auto-detect-new", file=sys.stderr)
        return 2

    if not args.dry_run and not args.skip_network_preflight:
        failed_hosts = _network_preflight(
            hosts=[
                "generativelanguage.googleapis.com",
                "www.blackstone.com",
                "bebeez.it",
            ]
        )
        if failed_hosts:
            print(
                "Error: network preflight failed (DNS resolution). "
                f"Unresolved hosts: {', '.join(failed_hosts)}",
                file=sys.stderr,
            )
            print(
                "Run this command in an environment with unrestricted networking "
                "(outside DNS-restricted sandbox mode), or use --skip-network-preflight "
                "only if DNS is intentionally blocked and you are running offline-only steps.",
                file=sys.stderr,
            )
            return 2

    slug_csv = ",".join(slugs)
    summary_path = _resolve_repo_path(args.summary_path)

    pipeline_cmd = f"pnpm pipeline --slugs {slug_csv}"
    if args.force_extract:
        pipeline_cmd += " --force-extract"

    stages: list[tuple[str, str]] = [
        ("pipeline", pipeline_cmd),
        (
            "enrich_portfolio_gemini",
            (
                "cd apps/worker && . .venv/bin/activate && "
                f"python3 scripts/enrich_portfolio_gemini_full.py --slugs {slug_csv} --limit 0"
            ),
        ),
        ("enrich_fund_metadata_gemini", f"python3 scripts/enrich-fund-metadata-gemini.py --slugs {slug_csv}"),
        (
            "audit_fund_assets_gemini",
            (
                "python3 scripts/audit-fund-assets-gemini.py "
                f"--slugs {slug_csv} "
                "--no-grounding "
                "--chunk-size 20 --chunk-split-sizes 20,8,1 "
                "--max-existing-names-in-missing-prompt 60 --missing-name-caps 60,20,1 "
                "--sleep-seconds 1 --timeout-sec 90 --hard-timeout-sec 120 --retries 3"
            ),
        ),
    ]

    results: list[StageResult] = []

    for stage_name, command in stages:
        result = _run_stage(stage_name, command, dry_run=args.dry_run)
        results.append(result)
        if result.status != "passed" and args.stop_on_fail:
            break

    if all(r.status == "passed" for r in results) and args.apply_missing_assets:
        result = _run_apply_missing_assets_stage(slugs, dry_run=args.dry_run)
        results.append(result)
        if result.status != "passed" and args.stop_on_fail:
            pass

    should_continue = all(r.status == "passed" for r in results) or not args.stop_on_fail
    if should_continue:
        for stage_name, command in [
            ("signals_to_portfolio", "pnpm pipeline:signals-to-portfolio"),
            (
                "verify_completion",
                (
                    "python3 scripts/verify_new_fund_completion.py "
                    f"--slugs {slug_csv} --output {REPORT_REL.as_posix()}"
                ),
            ),
        ]:
            result = _run_stage(stage_name, command, dry_run=args.dry_run)
            results.append(result)
            if result.status != "passed" and args.stop_on_fail:
                should_continue = False
                break

    if should_continue and args.apply_backfill:
        backfill_cmd = (
            "python3 scripts/backfill_top_aum_signals.py "
            f"--slugs {slug_csv} --top-n {args.backfill_top_n} "
            f"--min-signals {args.backfill_min_signals} --apply"
        )
        result = _run_stage("backfill_top_aum_signals", backfill_cmd, dry_run=args.dry_run)
        results.append(result)
        if result.status == "passed" or not args.stop_on_fail:
            result = _run_stage(
                "verify_completion_after_backfill",
                (
                    "python3 scripts/verify_new_fund_completion.py "
                    f"--slugs {slug_csv} --output {REPORT_REL.as_posix()}"
                ),
                dry_run=args.dry_run,
            )
            results.append(result)

    final_status = "passed" if all(r.status == "passed" for r in results) else "failed"
    summary: dict[str, Any] = {
        "generated_at": _now_iso(),
        "status": final_status,
        "slugs": slugs,
        "args": {
            "force_extract": args.force_extract,
            "apply_missing_assets": args.apply_missing_assets,
            "apply_backfill": args.apply_backfill,
            "backfill_top_n": args.backfill_top_n,
            "backfill_min_signals": args.backfill_min_signals,
            "stop_on_fail": args.stop_on_fail,
            "dry_run": args.dry_run,
        },
        "stages": [asdict(r) for r in results],
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nSummary written to: {summary_path}")
    print(f"Final status: {final_status}")

    return 0 if final_status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
