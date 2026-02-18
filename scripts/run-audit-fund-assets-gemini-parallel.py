#!/usr/bin/env python3
"""
Run Gemini fund-asset audit in parallel shards (multiple workers), then merge results.

Important:
- Uses separate output/progress files per worker to avoid write collisions.
- Resume-safe by default: does not reset shard files, merges pre-existing shard/master
  state, and skips strictly completed slugs inferred from master + shard outputs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gemini_audit_completion import is_fund_result_complete, load_verified_zero_italy_slugs

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVED = REPO_ROOT / "data" / "derived"
DB_PATH = REPO_ROOT / "data" / "db.json"
PORTFOLIO_PATH = DERIVED / "portfolio_items.json"
WORKER_SCRIPT = REPO_ROOT / "scripts" / "audit-fund-assets-gemini.py"

MASTER_OUTPUT_PATH = DERIVED / "gemini_fund_asset_audit.json"
MASTER_PROGRESS_PATH = DERIVED / "gemini_fund_asset_audit_progress.json"
DEFAULT_REMAINING_SLUGS_PATH = DERIVED / "gemini_fund_asset_remaining_slugs.txt"
DEFAULT_ZERO_ITALY_VERIFIED_PATH = DERIVED / "gemini_fund_asset_zero_italy_verified.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def sort_funds_by_aum_desc(funds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(f: dict[str, Any]) -> tuple[bool, float, str]:
        aum = f.get("aum_eur")
        has_no_aum = aum is None
        aum_num = float(aum) if isinstance(aum, (int, float)) else -1.0
        return (has_no_aum, -aum_num, (f.get("name") or f.get("slug") or "").lower())

    return sorted(funds, key=key)


def build_queue_slugs(db: dict[str, Any], portfolio: dict[str, Any]) -> list[str]:
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


def split_round_robin(items: list[str], workers: int) -> list[list[str]]:
    buckets: list[list[str]] = [[] for _ in range(workers)]
    for i, item in enumerate(items):
        buckets[i % workers].append(item)
    return [b for b in buckets if b]


def load_result_slugs_strict(path: Path, *, verified_zero_italy_slugs: set[str]) -> set[str]:
    if not path.exists():
        return set()
    payload = load_json(path)
    funds = payload.get("funds")
    if not isinstance(funds, list):
        return set()
    out: set[str] = set()
    for fund in funds:
        if not isinstance(fund, dict):
            continue
        slug = fund.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        is_complete, _ = is_fund_result_complete(
            fund,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        if is_complete:
            out.add(slug.strip())
    return out


def resolve_repo_relative_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def discover_shard_paths() -> tuple[list[Path], list[Path]]:
    outputs = sorted(DERIVED.glob("gemini_fund_asset_audit.shard*.json"))
    progresses = sorted(DERIVED.glob("gemini_fund_asset_audit_progress.shard*.json"))
    return outputs, progresses


def add_arg(cmd: list[str], name: str, value: Any) -> None:
    if value is None:
        return
    cmd.extend([name, str(value)])


def worker_paths(worker_idx: int) -> tuple[Path, Path, Path, Path]:
    slug_file = DERIVED / f"gemini_fund_asset_audit.shard{worker_idx}.slugs.txt"
    output_file = DERIVED / f"gemini_fund_asset_audit.shard{worker_idx}.json"
    progress_file = DERIVED / f"gemini_fund_asset_audit_progress.shard{worker_idx}.json"
    log_file = DERIVED / f"gemini_fund_asset_audit.shard{worker_idx}.log"
    return slug_file, output_file, progress_file, log_file


def merge_results(
    *,
    all_ordered_slugs: list[str],
    shard_output_paths: list[Path],
    shard_progress_paths: list[Path],
    master_output_path: Path,
    master_progress_path: Path,
    verified_zero_italy_slugs: set[str],
) -> None:
    if master_output_path.exists():
        master_output = load_json(master_output_path)
    else:
        master_output = {
            "generated_at": now_iso(),
            "model": "gemini-3-flash-preview",
            "funds": [],
            "summary": {},
        }

    existing_funds = master_output.get("funds")
    by_slug: dict[str, dict[str, Any]] = {}
    if isinstance(existing_funds, list):
        for fund in existing_funds:
            if isinstance(fund, dict) and isinstance(fund.get("slug"), str):
                by_slug[fund["slug"]] = fund

    for out_path in shard_output_paths:
        if not out_path.exists():
            continue
        shard = load_json(out_path)
        shard_funds = shard.get("funds")
        if not isinstance(shard_funds, list):
            continue
        for fund in shard_funds:
            if isinstance(fund, dict) and isinstance(fund.get("slug"), str):
                by_slug[fund["slug"]] = fund

    merged_funds = [by_slug[s] for s in all_ordered_slugs if s in by_slug]

    api_calls = 0
    api_failures = 0
    completed_strict: set[str] = set()
    incomplete_reason_counts: dict[str, int] = {}
    unverified_zero_italy_slugs: list[str] = []
    for fund in merged_funds:
        diagnostics = fund.get("call_diagnostics")
        if isinstance(diagnostics, list):
            api_calls += len(diagnostics)
            api_failures += sum(1 for d in diagnostics if isinstance(d, dict) and d.get("error"))
        is_complete, reasons = is_fund_result_complete(
            fund,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        slug = fund.get("slug")
        if isinstance(slug, str):
            if is_complete:
                completed_strict.add(slug)
            if "zero_italian_unverified" in reasons:
                unverified_zero_italy_slugs.append(slug)
        for reason in reasons:
            incomplete_reason_counts[reason] = incomplete_reason_counts.get(reason, 0) + 1

    master_output["generated_at"] = now_iso()
    master_output["funds"] = merged_funds
    master_output["summary"] = {
        "funds_in_queue": len(all_ordered_slugs),
        "funds_with_results": len(merged_funds),
        "funds_completed_strict": len([slug for slug in completed_strict if slug in set(all_ordered_slugs)]),
        "total_wrong_or_correction_issues": sum(len((f.get("wrong_or_correction_issues") or [])) for f in merged_funds),
        "total_missing_assets": sum(len((f.get("missing_assets") or [])) for f in merged_funds),
        "api_calls": api_calls,
        "api_failures": api_failures,
        "incomplete_reason_counts": dict(sorted(incomplete_reason_counts.items())),
        "unverified_zero_italy_slugs": sorted(set(unverified_zero_italy_slugs)),
        "zero_italy_verified_slugs_count": len(verified_zero_italy_slugs),
        "updated_at": now_iso(),
    }
    save_json_atomic(master_output_path, master_output)

    if master_progress_path.exists():
        master_progress = load_json(master_progress_path)
    else:
        master_progress = {
            "started_at": now_iso(),
            "completed_slugs": [],
            "failed": {},
            "last_slug": None,
            "updated_at": now_iso(),
        }

    completed = set(completed_strict)
    failed: dict[str, Any] = master_progress.get("failed") if isinstance(master_progress.get("failed"), dict) else {}

    for p_path in shard_progress_paths:
        if not p_path.exists():
            continue
        p = load_json(p_path)
        shard_failed = p.get("failed")
        if isinstance(shard_failed, dict):
            for slug, err in shard_failed.items():
                failed[str(slug)] = err
        if p.get("last_slug"):
            master_progress["last_slug"] = p.get("last_slug")

    for slug in completed:
        failed.pop(slug, None)

    master_progress["completed_slugs"] = sorted(completed)
    master_progress["failed"] = failed
    master_progress["updated_at"] = now_iso()
    master_progress["incomplete_reason_counts"] = dict(sorted(incomplete_reason_counts.items()))
    master_progress["unverified_zero_italy_slugs"] = sorted(set(unverified_zero_italy_slugs))
    master_progress["zero_italy_verified_slugs_count"] = len(verified_zero_italy_slugs)
    save_json_atomic(master_progress_path, master_progress)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fund-asset Gemini audit in parallel shards.")
    parser.add_argument("--workers", type=int, default=2, help="Number of parallel workers")
    parser.add_argument("--limit-funds", type=int, default=0, help="Cap number of remaining funds to process")
    parser.add_argument("--include-completed", action="store_true", help="Include already completed slugs from master progress")
    parser.add_argument(
        "--resume-from-shards",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When selecting remaining slugs, include shard outputs in strict completed-skip set",
    )
    parser.add_argument(
        "--reset-shards",
        action="store_true",
        help="Reset shard output/progress for this run (not recommended for resumable runs)",
    )
    parser.add_argument(
        "--remaining-slugs-path",
        type=str,
        default=str(DEFAULT_REMAINING_SLUGS_PATH.relative_to(REPO_ROOT)),
        help="Write current remaining slugs to this path",
    )
    parser.add_argument(
        "--zero-italy-verified-path",
        type=str,
        default=str(DEFAULT_ZERO_ITALY_VERIFIED_PATH.relative_to(REPO_ROOT)),
        help="Path to JSON/TXT whitelist for funds verified to have no Italy assets",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print planned shards")

    # Forwarded worker settings
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--chunk-size", type=int, default=40)
    parser.add_argument("--chunk-split-sizes", type=str, default="40,20,8,1")
    parser.add_argument("--max-entries-per-fund", type=int, default=0)
    parser.add_argument("--max-existing-names-in-missing-prompt", type=int, default=500)
    parser.add_argument("--missing-name-caps", type=str, default="500,300,150,60")
    parser.add_argument("--sleep-seconds", type=float, default=3.0)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--hard-timeout-sec", type=int, default=150)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--min-backoff-sec", type=float, default=2.0)
    parser.add_argument("--max-backoff-sec", type=float, default=20.0)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--no-grounding", action="store_true")

    args = parser.parse_args()

    if args.workers <= 0:
        print("Error: --workers must be > 0", file=sys.stderr)
        return 2

    db = load_json(DB_PATH)
    portfolio = load_json(PORTFOLIO_PATH)
    all_ordered_slugs = build_queue_slugs(db, portfolio)
    remaining_slugs_path = resolve_repo_relative_path(args.remaining_slugs_path)
    verified_zero_italy_slugs = load_verified_zero_italy_slugs(
        resolve_repo_relative_path(args.zero_italy_verified_path)
    )
    all_ordered_slug_set = set(all_ordered_slugs)

    completed = set()
    if not args.include_completed:
        if args.resume_from_shards:
            shard_outputs, shard_progresses = discover_shard_paths()
            if shard_outputs or shard_progresses:
                merge_results(
                    all_ordered_slugs=all_ordered_slugs,
                    shard_output_paths=shard_outputs,
                    shard_progress_paths=shard_progresses,
                    master_output_path=MASTER_OUTPUT_PATH,
                    master_progress_path=MASTER_PROGRESS_PATH,
                    verified_zero_italy_slugs=verified_zero_italy_slugs,
                )
                print("Pre-merged master with discovered shard files for resume safety.")
        completed |= load_result_slugs_strict(
            MASTER_OUTPUT_PATH,
            verified_zero_italy_slugs=verified_zero_italy_slugs,
        )
        if args.resume_from_shards:
            shard_outputs, shard_progresses = discover_shard_paths()
            for out_path in shard_outputs:
                completed |= load_result_slugs_strict(
                    out_path,
                    verified_zero_italy_slugs=verified_zero_italy_slugs,
                )

    completed = {slug for slug in completed if slug in all_ordered_slug_set}

    remaining = [s for s in all_ordered_slugs if s not in completed]
    if args.limit_funds > 0:
        remaining = remaining[:args.limit_funds]

    remaining_slugs_path.parent.mkdir(parents=True, exist_ok=True)
    remaining_slugs_path.write_text("\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8")
    print(f"Wrote remaining slugs -> {remaining_slugs_path} ({len(remaining)})")

    if not remaining:
        print("No remaining funds to process.")
        return 0

    shards = split_round_robin(remaining, args.workers)
    print(
        f"Remaining funds: {len(remaining)} | workers={len(shards)} | "
        f"completed_skipped={len(completed)}"
    )
    for i, shard in enumerate(shards, 1):
        print(f"  Worker {i}: {len(shard)} slugs (first: {shard[0]})")

    if args.dry_run:
        return 0

    processes: list[tuple[int, subprocess.Popen[Any], Path, Path, Path, Path, Any]] = []
    shard_output_paths: list[Path] = []
    shard_progress_paths: list[Path] = []

    for i, shard in enumerate(shards, 1):
        slug_file, out_file, prog_file, log_file = worker_paths(i)
        slug_file.write_text("\n".join(shard) + "\n", encoding="utf-8")
        shard_output_paths.append(out_file)
        shard_progress_paths.append(prog_file)

        cmd = [
            "python3",
            "-u",
            str(WORKER_SCRIPT.relative_to(REPO_ROOT)),
            "--slugs-file", str(slug_file),
            "--output-path", str(out_file),
            "--progress-path", str(prog_file),
        ]
        if args.reset_shards:
            cmd.append("--reset")
        add_arg(cmd, "--model", args.model)
        add_arg(cmd, "--chunk-size", args.chunk_size)
        add_arg(cmd, "--chunk-split-sizes", args.chunk_split_sizes)
        add_arg(cmd, "--max-entries-per-fund", args.max_entries_per_fund)
        add_arg(cmd, "--max-existing-names-in-missing-prompt", args.max_existing_names_in_missing_prompt)
        add_arg(cmd, "--missing-name-caps", args.missing_name_caps)
        add_arg(cmd, "--sleep-seconds", args.sleep_seconds)
        add_arg(cmd, "--timeout-sec", args.timeout_sec)
        add_arg(cmd, "--hard-timeout-sec", args.hard_timeout_sec)
        add_arg(cmd, "--retries", args.retries)
        add_arg(cmd, "--min-backoff-sec", args.min_backoff_sec)
        add_arg(cmd, "--max-backoff-sec", args.max_backoff_sec)
        add_arg(cmd, "--max-output-tokens", args.max_output_tokens)
        add_arg(cmd, "--temperature", args.temperature)
        add_arg(cmd, "--zero-italy-verified-path", args.zero_italy_verified_path)
        if args.no_grounding:
            cmd.append("--no-grounding")

        log_mode = "w" if args.reset_shards else "a"
        log_fp = open(log_file, log_mode, encoding="utf-8")
        if log_mode == "a":
            log_fp.write(f"\n=== resume @ {now_iso()} ===\n")
            log_fp.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        processes.append((i, proc, slug_file, out_file, prog_file, log_file, log_fp))
        print(f"Started worker {i} (pid={proc.pid}) -> {log_file}")

    failures = 0
    while processes:
        still_running: list[tuple[int, subprocess.Popen[Any], Path, Path, Path, Path, Any]] = []
        for i, proc, slug_file, out_file, prog_file, log_file, log_fp in processes:
            rc = proc.poll()
            if rc is None:
                still_running.append((i, proc, slug_file, out_file, prog_file, log_file, log_fp))
                continue
            try:
                log_fp.flush()
                log_fp.close()
            except Exception:
                pass
            if rc != 0:
                failures += 1
            print(f"Worker {i} finished rc={rc} (log: {log_file})")
        processes = still_running
        if processes:
            time.sleep(2)

    all_shard_output_paths, all_shard_progress_paths = discover_shard_paths()
    merge_results(
        all_ordered_slugs=all_ordered_slugs,
        shard_output_paths=all_shard_output_paths or shard_output_paths,
        shard_progress_paths=all_shard_progress_paths or shard_progress_paths,
        master_output_path=MASTER_OUTPUT_PATH,
        master_progress_path=MASTER_PROGRESS_PATH,
        verified_zero_italy_slugs=verified_zero_italy_slugs,
    )
    print(f"Merged output -> {MASTER_OUTPUT_PATH}")
    print(f"Merged progress -> {MASTER_PROGRESS_PATH}")

    if failures > 0:
        print(f"Completed with worker failures: {failures}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
