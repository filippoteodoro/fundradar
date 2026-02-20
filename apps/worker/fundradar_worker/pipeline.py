#!/usr/bin/env python3
"""
Fundradar pipeline orchestrator.

Runs the full monitoring pipeline in dependency order:
  1. monitor               - fetch websites, extract data, generate raw signals
  2. rss                   - fetch Italian news RSS feeds, match to funds, append signals
  3. normalize_sectors     - normalize sectors to canonical taxonomy
  4. normalize_portfolio   - normalize company data across fund portfolios
  5. enrich_portfolio      - fill missing sector/HQ/description via Gemini (optional)
  6. filter                - quality-score signals and remove noise
  7. enrich                - add AI summaries via OpenAI
  8. signal_to_portfolio   - convert deal/exit signals to portfolio entries (local, reads from step 7)

Each step validates its output before proceeding to the next.

Usage:
    python -m fundradar_worker.pipeline           # full pipeline
    python -m fundradar_worker.pipeline --step monitor   # single step
    python -m fundradar_worker.pipeline --dry-run        # validate only
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .io_utils import backup_before_write
from .alerting import AlertConfig, AlertManager, Alert

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "derived"
WORKER_DIR = PROJECT_ROOT / "apps" / "worker"
SUMMARY_REPORT_PATH = DATA_DIR / "signal_summary_report.json"
DB_PATH = PROJECT_ROOT / "data" / "db.json"

# Pipeline step definitions
# Order: monitor -> rss -> normalize_sectors -> normalize_portfolio -> enrich_portfolio (optional) -> filter -> enrich signals
STEPS = [
    {
        "name": "monitor",
        "description": "Fetch websites and generate signals",
        "command": [sys.executable, "-m", "fundradar_worker.monitor", "--extractor-urls"],
        "cwd": str(WORKER_DIR),
        "outputs": [
            DATA_DIR / "detected_signals.json",
            DATA_DIR / "portfolio_items.json",
        ],
        "timeout": 30 * 60,  # 30 min — large number of websites
    },
    {
        "name": "rss",
        "description": "Fetch Italian news RSS feeds and match to tracked funds",
        "command": [sys.executable, "-m", "fundradar_worker.rss_monitor"],
        "cwd": str(WORKER_DIR),
        "outputs": [
            DATA_DIR / "detected_signals.json",
        ],
        "optional": True,
        "timeout": 5 * 60,  # 5 min
    },
    {
        "name": "normalize_sectors",
        "description": "Normalize fund + company sectors to canonical taxonomy",
        "command": [sys.executable, "scripts/normalize_sectors.py"],
        "cwd": str(WORKER_DIR),
        "outputs": [
            DATA_DIR / "portfolio_items.json",
        ],
        "timeout": 2 * 60,  # 2 min — local JSON transform
    },
    {
        "name": "normalize_portfolio",
        "description": "Normalize company data across fund portfolios",
        "command": [sys.executable, "scripts/normalize_portfolio_cross_fund.py"],
        "cwd": str(WORKER_DIR),
        "outputs": [
            DATA_DIR / "portfolio_items.json",
        ],
        "timeout": 2 * 60,  # 2 min — local JSON transform
    },
    {
        "name": "enrich_portfolio",
        "description": "Enrich portfolio entries with sector/HQ/description (Gemini)",
        "command": [sys.executable, "scripts/enrich_portfolio_gemini_full.py", "--pipeline"],
        "cwd": str(WORKER_DIR),
        "outputs": [
            DATA_DIR / "portfolio_items.json",
        ],
        "optional": True,
        "timeout": 15 * 60,  # 15 min — API calls with auto-retry
        "retry_on_partial": True,  # retry if exit code 2 (partial success)
        "max_retries": 2,  # up to 2 retries (3 total attempts)
    },
    {
        "name": "filter",
        "description": "Score and filter signal quality (free, local)",
        "command": [sys.executable, "scripts/filter_signals.py"],
        "cwd": str(WORKER_DIR),
        "outputs": [
            DATA_DIR / "detected_signals_filtered.json",
        ],
        "timeout": 5 * 60,  # 5 min
    },
    {
        "name": "enrich",
        "description": "Add AI summaries to filtered signals (OpenAI API)",
        "command": [sys.executable, "scripts/enrich_signals_openai.py"],
        "cwd": str(WORKER_DIR),
        "outputs": [
            DATA_DIR / "detected_signals_enriched.json",
        ],
        "timeout": 20 * 60,  # 20 min — API calls for 300+ signals
        "retry_on_partial": True,
        "max_retries": 2,
    },
    {
        "name": "signal_to_portfolio",
        "description": "Convert deal/exit signals into portfolio entries (local, no API)",
        "command": [sys.executable, "scripts/signal_to_portfolio.py", "--pipeline"],
        "cwd": str(WORKER_DIR),
        "outputs": [DATA_DIR / "portfolio_items.json"],
        "timeout": 2 * 60,  # 2 min — purely local, reads pre-extracted target_companies
    },
]


def _validate_output(path: Path) -> tuple[bool, str]:
    """Check that an output file exists, is valid JSON, and is non-empty."""
    if not path.exists():
        return False, f"Missing: {path.name}"
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and not data:
            return False, f"Empty dict: {path.name}"
        if isinstance(data, list) and not data:
            return False, f"Empty list: {path.name}"
        return True, f"OK: {path.name} ({path.stat().st_size:,} bytes)"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in {path.name}: {e}"


def _load_json_if_exists(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _load_funds() -> list[dict]:
    if not DB_PATH.exists():
        return []
    try:
        with open(DB_PATH) as f:
            data = json.load(f)
        return data.get("funds", []) if isinstance(data, dict) else []
    except Exception:
        return []


def _quality_stats(signals: list[dict]) -> dict:
    qual = [s.get("quality_score") for s in signals if isinstance(s.get("quality_score"), int)]
    if not qual:
        return {}
    avg = sum(qual) / len(qual)
    buckets = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    for q in qual:
        if q <= 20:
            buckets["0-20"] += 1
        elif q <= 40:
            buckets["21-40"] += 1
        elif q <= 60:
            buckets["41-60"] += 1
        elif q <= 80:
            buckets["61-80"] += 1
        else:
            buckets["81-100"] += 1
    return {"avg": round(avg, 2), "buckets": buckets}


def write_summary_report() -> dict | None:
    """Generate and persist a concise summary report for signals pipeline outputs."""
    raw_path = DATA_DIR / "detected_signals.json"
    filtered_path = DATA_DIR / "detected_signals_filtered.json"
    enriched_path = DATA_DIR / "detected_signals_enriched.json"

    raw = _load_json_if_exists(raw_path)
    filtered = _load_json_if_exists(filtered_path)
    enriched = _load_json_if_exists(enriched_path)
    funds = _load_funds()

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw": {
            "path": str(raw_path),
            "count": len(raw.get("signals", [])) if raw else None,
            "exists": bool(raw),
        },
        "filtered": {
            "path": str(filtered_path),
            "count": len(filtered.get("signals", [])) if filtered else None,
            "exists": bool(filtered),
            "filter_stats": filtered.get("filter_stats") if filtered else None,
            "cleanup_stats": filtered.get("cleanup_stats") if filtered else None,
            "filtered_at": filtered.get("filtered_at") if filtered else None,
            "cleanup_at": filtered.get("cleanup_at") if filtered else None,
        },
        "enriched": {
            "path": str(enriched_path),
            "count": len(enriched.get("signals", [])) if enriched else None,
            "exists": bool(enriched),
            "enriched_at": enriched.get("enriched_at") if enriched else None,
            "llm_filter_stats": enriched.get("llm_filter_stats") if enriched else None,
        },
    }

    # Coverage report: which funds have signals (filtered) vs none
    if funds:
        fund_slugs = [f.get("slug") for f in funds if f.get("slug")]
        raw_signals = raw.get("signals", []) if raw else []
        filtered_signals = filtered.get("signals", []) if filtered else []

        raw_counts: dict[str, int] = {}
        filtered_counts: dict[str, int] = {}
        for s in raw_signals:
            slug = s.get("fund_slug")
            if slug:
                raw_counts[slug] = raw_counts.get(slug, 0) + 1
        for s in filtered_signals:
            slug = s.get("fund_slug")
            if slug:
                filtered_counts[slug] = filtered_counts.get(slug, 0) + 1

        no_signals = [slug for slug in fund_slugs if filtered_counts.get(slug, 0) == 0]
        no_raw = [slug for slug in fund_slugs if raw_counts.get(slug, 0) == 0]
        raw_but_filtered = [slug for slug in fund_slugs if raw_counts.get(slug, 0) > 0 and filtered_counts.get(slug, 0) == 0]

        coverage_counts = [
            {
                "slug": slug,
                "raw": raw_counts.get(slug, 0),
                "filtered": filtered_counts.get(slug, 0),
            }
            for slug in fund_slugs
        ]

        report["coverage"] = {
            "fund_total": len(fund_slugs),
            "funds_with_signals": len(fund_slugs) - len(no_signals),
            "funds_no_signals": len(no_signals),
            "funds_no_raw": len(no_raw),
            "funds_raw_but_filtered": len(raw_but_filtered),
            "no_raw_slugs": no_raw,
            "raw_but_filtered_slugs": raw_but_filtered,
            "counts": coverage_counts,
        }

    if enriched and isinstance(enriched.get("signals"), list):
        signals = enriched.get("signals", [])
        llm_keep_counts = {
            "true": sum(1 for s in signals if s.get("llm_keep") is True),
            "false": sum(1 for s in signals if s.get("llm_keep") is False),
            "none": sum(1 for s in signals if s.get("llm_keep") is None),
        }
        llm_keep_source = {}
        for s in signals:
            src = s.get("llm_keep_source") or "none"
            llm_keep_source[src] = llm_keep_source.get(src, 0) + 1
        italy_relevant = sum(1 for s in signals if s.get("italy_relevant") is True)
        llm_filtered_out = 0
        llm_filter_stats = enriched.get("llm_filter_stats") if enriched else None
        if isinstance(llm_filter_stats, dict):
            llm_filtered_out = llm_filter_stats.get("filtered_out") or 0
        llm_keep_false_retained = max(0, llm_keep_counts.get("false", 0) - llm_filtered_out)

        report["enriched"].update({
            "llm_keep_counts": llm_keep_counts,
            "llm_keep_source": llm_keep_source,
            "italy_relevant_true": italy_relevant,
            "llm_keep_false_retained": llm_keep_false_retained,
        })

    if filtered and isinstance(filtered.get("signals"), list):
        filtered_signals = filtered.get("signals", [])
        quality_stats = _quality_stats(filtered_signals)
        if filtered_signals:
            good_90 = sum(1 for s in filtered_signals if (s.get("quality_score") or 0) >= 90)
            quality_stats["good_90_count"] = good_90
            quality_stats["good_90_pct"] = round((good_90 / len(filtered_signals)) * 100, 2)
        report["filtered"]["quality"] = quality_stats

    try:
        with open(SUMMARY_REPORT_PATH, "w") as f:
            json.dump(report, f, indent=2)
    except Exception:
        return None

    return report


def _portfolio_enrichment_status() -> dict | None:
    """Check how many portfolio entries still need Gemini enrichment."""
    portfolio_path = DATA_DIR / "portfolio_items.json"
    progress_path = DATA_DIR / "enrichment_portfolio_full_progress.json"
    if not portfolio_path.exists():
        return None
    try:
        with open(portfolio_path) as f:
            portfolio = json.load(f)
        done_keys = set()
        if progress_path.exists():
            with open(progress_path) as f:
                progress = json.load(f)
            done_keys = set(progress.get("done", {}).keys())

        fund_stats: list[dict] = []
        total_remaining = 0
        for slug, entries in sorted(portfolio.get("fund_portfolios", {}).items()):
            needs = {"count": 0, "sector": 0, "hq": 0, "desc": 0}
            for e in entries:
                key = f"{slug}::{e.get('name', '')}"
                if key in done_keys:
                    continue
                missing_s = not e.get("sector")
                missing_h = not e.get("headquarters")
                missing_d = not e.get("description")
                if missing_s or missing_h or missing_d:
                    needs["count"] += 1
                    if missing_s:
                        needs["sector"] += 1
                    if missing_h:
                        needs["hq"] += 1
                    if missing_d:
                        needs["desc"] += 1
            if needs["count"] > 0:
                fund_stats.append({"slug": slug, **needs})
                total_remaining += needs["count"]

        # Sort by count descending
        fund_stats.sort(key=lambda x: x["count"], reverse=True)
        batch_size = 25  # matches BATCH_SIZE in enrich_portfolio_gemini_full.py
        remaining_calls = sum((f["count"] + batch_size - 1) // batch_size for f in fund_stats)

        return {
            "remaining_entries": total_remaining,
            "remaining_calls": remaining_calls,
            "top_funds": fund_stats,
        }
    except Exception:
        return None


def _signal_to_portfolio_status() -> dict | None:
    """Check how many deal/exit signals still need portfolio conversion."""
    enriched_path = DATA_DIR / "detected_signals_enriched.json"
    progress_path = DATA_DIR / "signal_to_portfolio_progress.json"
    if not enriched_path.exists():
        return None
    try:
        with open(enriched_path) as f:
            enriched = json.load(f)
        signals = enriched.get("signals", [])
        deal_types = {"deal_announced", "exit_announced"}
        deal_signals = [
            s for s in signals
            if s.get("signal_type") in deal_types
            and s.get("fund_slug") and s.get("id")
            and (s.get("quality_score", 0) or 0) >= 60
        ]
        processed_ids = set()
        if progress_path.exists():
            with open(progress_path) as f:
                progress = json.load(f)
            processed_ids = set(progress.get("processed_signal_ids", []))
        remaining = [s for s in deal_signals if s["id"] not in processed_ids]
        return {
            "total_signals": len(deal_signals),
            "processed": len(deal_signals) - len(remaining),
            "remaining": len(remaining),
        }
    except Exception:
        return None


def _suggest_reruns(report: dict | None) -> list[tuple[str, str]]:
    """Generate actionable re-run commands based on pipeline state."""
    suggestions: list[tuple[str, str]] = []

    # Check portfolio enrichment
    portfolio_status = _portfolio_enrichment_status()
    if portfolio_status and portfolio_status["remaining_entries"] > 0:
        remaining = portfolio_status["remaining_entries"]
        suggestions.append((
            f"Portfolio enrichment incomplete ({remaining} entries remaining)",
            "python apps/worker/scripts/enrich_portfolio_gemini_full.py --pipeline",
        ))

    # Check signal enrichment gaps
    if report:
        enriched = report.get("enriched", {})
        llm_counts = enriched.get("llm_keep_counts") or {}
        none_count = llm_counts.get("none", 0)
        if none_count > 0:
            suggestions.append((
                f"Signal enrichment incomplete ({none_count} signals without keep/drop decision)",
                "python apps/worker/scripts/enrich_signals_openai.py",
            ))

        # Check for filtered-but-no-enriched gap
        filtered_count = report.get("filtered", {}).get("count") or 0
        enriched_count = enriched.get("count") or 0
        gap = filtered_count - enriched_count
        if gap > 5:
            llm_stats = enriched.get("llm_filter_stats") or {}
            hard_filtered = llm_stats.get("filtered_out", 0)
            unexplained = gap - hard_filtered
            if unexplained > 2:
                suggestions.append((
                    f"Filtered→Enriched gap: {gap} signals lost ({hard_filtered} LLM-filtered, {unexplained} unexplained)",
                    "python apps/worker/scripts/enrich_signals_openai.py",
                ))

    return suggestions


def _send_pipeline_alert(
    results: dict[str, bool],
    retry_log: dict[str, int],
    step_details: dict[str, dict],
    report: dict | None,
    elapsed: float,
):
    """Send a Telegram alert summarizing the pipeline run.

    Only sends if there are issues (failures, retries, remaining work).
    A fully clean run sends a brief success summary.
    """
    config = AlertConfig.from_env()
    if not config.telegram_enabled:
        return

    manager = AlertManager(config)

    failed_steps = [n for n, ok in results.items() if not ok]
    retried_steps = list(retry_log.keys())
    skipped_steps = [
        n for n, detail in step_details.items()
        if detail.get("skipped")
    ]

    # Determine overall status
    has_issues = bool(failed_steps or retried_steps or skipped_steps)

    # Check remaining enrichment work
    remaining_work: list[str] = []
    portfolio_status = _portfolio_enrichment_status()
    if portfolio_status and portfolio_status["remaining_entries"] > 0:
        remaining_work.append(
            f"Portfolio enrichment: {portfolio_status['remaining_entries']} entries remaining"
        )

    # Check signal-to-portfolio remaining work
    stp_status = _signal_to_portfolio_status()
    if stp_status and stp_status["remaining"] > 0:
        remaining_work.append(
            f"Signal→Portfolio: {stp_status['remaining']} signals remaining "
            f"({stp_status['processed']}/{stp_status['total_signals']} done)"
        )

    if report:
        enriched = report.get("enriched", {})
        llm_counts = enriched.get("llm_keep_counts") or {}
        none_count = llm_counts.get("none", 0)
        if none_count > 0:
            remaining_work.append(
                f"Signal enrichment: {none_count} signals without decision"
            )
        # Check filtered→enriched gap
        filtered_count = report.get("filtered", {}).get("count") or 0
        enriched_count = enriched.get("count") or 0
        gap = filtered_count - enriched_count
        llm_filtered = (enriched.get("llm_filter_stats") or {}).get("filtered_out", 0)
        unexplained = gap - llm_filtered
        if unexplained > 5:
            remaining_work.append(
                f"Filtered→Enriched gap: {gap} signals ({unexplained} unexplained)"
            )

    has_issues = has_issues or bool(remaining_work)

    # Build message
    lines: list[str] = []
    elapsed_min = elapsed / 60

    if not has_issues:
        # Clean run — brief success summary
        lines.append(f"Pipeline completed in {elapsed_min:.1f}m")
        if report:
            raw_n = report.get("raw", {}).get("count", "?")
            filt_n = report.get("filtered", {}).get("count", "?")
            enr_n = report.get("enriched", {}).get("count", "?")
            lines.append(f"Signals: {raw_n} raw → {filt_n} filtered → {enr_n} enriched")
        title = "Pipeline OK"
        level = "info"
    else:
        lines.append(f"Pipeline finished in {elapsed_min:.1f}m with issues:\n")

        if failed_steps:
            lines.append("*Failed steps:*")
            for name in failed_steps:
                detail = step_details.get(name, {})
                reason = detail.get("reason", "unknown error")
                lines.append(f"  • {name}: {reason}")
            lines.append("")

        if retried_steps:
            lines.append("*Retried steps:*")
            for name in retried_steps:
                lines.append(f"  • {name}: {retry_log[name]} retries used")
            lines.append("")

        if skipped_steps:
            lines.append("*Skipped (optional):*")
            for name in skipped_steps:
                detail = step_details.get(name, {})
                reason = detail.get("reason", "failed")
                lines.append(f"  • {name}: {reason}")
            lines.append("")

        if remaining_work:
            lines.append("*Remaining work:*")
            for item in remaining_work:
                lines.append(f"  • {item}")
            lines.append("")

        if report:
            raw_n = report.get("raw", {}).get("count", "?")
            filt_n = report.get("filtered", {}).get("count", "?")
            enr_n = report.get("enriched", {}).get("count", "?")
            lines.append(f"Signals: {raw_n} raw → {filt_n} filtered → {enr_n} enriched")

        title = f"Pipeline Issues: {len(failed_steps)} failed, {len(retried_steps)} retried"
        if not failed_steps and not retried_steps:
            title = f"Pipeline: {len(remaining_work)} items need attention"
        level = "error" if failed_steps else "warning"

    manager.add_alert(Alert(
        title=title,
        message="\n".join(lines),
        level=level,
        source="pipeline",
    ))
    manager.send_pending_alerts()


def run_step(step: dict, dry_run: bool = False) -> tuple[bool, int]:
    """Run a single pipeline step with backup, timeout, and validation.

    Returns (success: bool, exit_code: int). exit_code is -1 on timeout/launch failure.
    """
    name = step["name"]
    step_timeout = step.get("timeout")
    print(f"\n{'=' * 60}")
    print(f"  Step: {name} - {step['description']}")
    if step_timeout:
        print(f"  Timeout: {step_timeout // 60}m {step_timeout % 60}s")
    print(f"{'=' * 60}")

    # Back up outputs before overwriting
    for output_path in step["outputs"]:
        if output_path.exists():
            backup_before_write(output_path)
            print(f"  Backed up: {output_path.name}")

    if dry_run:
        print(f"  [dry-run] Would run: {' '.join(step['command'])}")
        return True, 0

    # Run the command with optional timeout
    start = time.monotonic()
    try:
        result = subprocess.run(
            step["command"],
            cwd=step["cwd"],
            capture_output=False,
            text=True,
            timeout=step_timeout,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        print(f"\n  TIMEOUT after {elapsed:.1f}s (limit: {step_timeout}s)")
        if step.get("optional"):
            print(f"  SKIPPED: {name} timed out (optional step)")
            return True, -1
        print(f"  FAILED: {name} timed out")
        return False, -1
    except Exception as e:
        print(f"  FAILED to launch: {e}")
        return False, -1

    elapsed = time.monotonic() - start
    print(f"\n  Finished in {elapsed:.1f}s (exit code {result.returncode})")

    if result.returncode != 0:
        if step.get("optional"):
            print(f"  SKIPPED: {name} exited with code {result.returncode} (optional step)")
            return True, result.returncode
        # Exit code 2 = partial success (e.g. some batches failed but progress was made)
        if result.returncode == 2 and step.get("retry_on_partial"):
            print(f"  PARTIAL: {name} exited with code 2 (partial success, retryable)")
            return False, result.returncode
        print(f"  FAILED: {name} exited with code {result.returncode}")
        return False, result.returncode

    # Validate outputs
    all_ok = True
    for output_path in step["outputs"]:
        ok, msg = _validate_output(output_path)
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {msg}")
        if not ok:
            all_ok = False

    return all_ok, result.returncode


def run_pipeline(only_step: str | None = None, dry_run: bool = False):
    """Run the full pipeline or a single step.

    Enrichment steps with retry_on_partial=True are automatically retried
    (up to max_retries times) when they exit with code 2 (partial success).
    The scripts are idempotent — progress files skip already-done work.
    """
    print(f"Fundradar Pipeline - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Data dir: {DATA_DIR}")

    steps_to_run = STEPS
    if only_step:
        steps_to_run = [s for s in STEPS if s["name"] == only_step]
        if not steps_to_run:
            valid = ", ".join(s["name"] for s in STEPS)
            print(f"Unknown step: {only_step}. Valid steps: {valid}")
            sys.exit(1)

    total_start = time.monotonic()
    results = {}
    retry_log: dict[str, int] = {}  # step_name → number of retries used
    step_details: dict[str, dict] = {}  # step_name → {reason, skipped, exit_code}

    for step in steps_to_run:
        max_retries = step.get("max_retries", 0) if step.get("retry_on_partial") else 0
        attempt = 0

        while True:
            ok, exit_code = run_step(step, dry_run=dry_run)

            if ok:
                results[step["name"]] = True
                # Track optional steps that returned non-zero but were counted as ok
                if exit_code != 0 and step.get("optional"):
                    reason = f"timeout (exit {exit_code})" if exit_code == -1 else f"exit code {exit_code}"
                    step_details[step["name"]] = {"skipped": True, "reason": reason, "exit_code": exit_code}
                break

            # Check if we should retry
            can_retry = (
                not dry_run
                and step.get("retry_on_partial")
                and exit_code == 2
                and attempt < max_retries
            )

            if can_retry:
                # Verify output files exist (partial success, not hard crash)
                outputs_exist = all(p.exists() for p in step["outputs"])
                if outputs_exist:
                    attempt += 1
                    retry_log[step["name"]] = attempt
                    print(f"\n  Auto-retry {attempt}/{max_retries} for {step['name']} in 5s...")
                    time.sleep(5)
                    continue

            # No retry — record failure
            results[step["name"]] = False

            # For optional or retryable enrichment steps, don't halt pipeline
            if step.get("optional") or (step.get("retry_on_partial") and exit_code == 2):
                if not step.get("optional"):
                    print(f"  {step['name']}: retries exhausted, continuing pipeline (enrichment is best-effort)")
                    results[step["name"]] = True  # Don't count as pipeline failure
                    step_details[step["name"]] = {
                        "skipped": False,
                        "reason": f"retries exhausted (exit code {exit_code})",
                        "exit_code": exit_code,
                    }
                else:
                    step_details[step["name"]] = {
                        "skipped": True,
                        "reason": f"optional step failed (exit code {exit_code})",
                        "exit_code": exit_code,
                    }
                break

            # Hard failure on non-optional step — halt pipeline
            step_details[step["name"]] = {
                "skipped": False,
                "reason": f"timeout" if exit_code == -1 else f"exit code {exit_code}",
                "exit_code": exit_code,
            }
            print(f"\n  Pipeline halted: {step['name']} failed.")
            break

        if results.get(step["name"]) is False and not step.get("optional") and not step.get("retry_on_partial"):
            break  # Stop pipeline on hard failure

    # Summary
    total_elapsed = time.monotonic() - total_start
    print(f"\n{'=' * 60}")
    print(f"  Pipeline Summary ({total_elapsed:.1f}s total)")
    print(f"{'=' * 60}")
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        retry_info = f" ({retry_log[name]} retries)" if name in retry_log else ""
        print(f"  [{status}] {name}{retry_info}")
    if step_details:
        print("\n  Step notes:")
        for name, detail in step_details.items():
            note_kind = "SKIP" if detail.get("skipped") else "WARN"
            reason = detail.get("reason", "n/a")
            exit_code = detail.get("exit_code")
            exit_suffix = f", exit={exit_code}" if exit_code is not None else ""
            print(f"  [{note_kind}] {name}: {reason}{exit_suffix}")

    failed = [n for n, ok in results.items() if not ok]
    if failed:
        print(f"\n  {len(failed)} step(s) failed.")
        if not dry_run:
            _send_pipeline_alert(results, retry_log, step_details, None, total_elapsed)
        sys.exit(1)
    else:
        if not dry_run:
            report = write_summary_report()
            if report:
                print(f"\n{'=' * 60}")
                print("  Signals Summary")
                print(f"{'=' * 60}")
                raw = report.get("raw", {})
                filtered = report.get("filtered", {})
                enriched = report.get("enriched", {})
                print(f"  Raw signals: {raw.get('count')}")
                print(f"  Filtered signals: {filtered.get('count')}")
                print(f"  Enriched signals: {enriched.get('count')}")
                llm_counts = enriched.get("llm_keep_counts") or {}
                print(f"  LLM keep: true={llm_counts.get('true')} false={llm_counts.get('false')} none={llm_counts.get('none')}")

                # Coverage summary
                coverage = report.get("coverage", {})
                if coverage:
                    print(f"  Fund coverage: {coverage.get('funds_with_signals', 0)}/{coverage.get('fund_total', 0)} funds with signals")
                    no_raw = coverage.get("funds_no_raw", 0)
                    raw_but_filtered = coverage.get("funds_raw_but_filtered", 0)
                    if no_raw:
                        print(f"  No raw signals: {no_raw} funds (need extractors)")
                    if raw_but_filtered:
                        print(f"  All filtered out: {raw_but_filtered} funds (signals exist but below quality threshold)")

                # Enrichment source breakdown
                llm_source = enriched.get("llm_keep_source") or {}
                if llm_source:
                    parts = [f"{src}={cnt}" for src, cnt in sorted(llm_source.items())]
                    print(f"  Enrichment sources: {', '.join(parts)}")

                print(f"  Report saved: {SUMMARY_REPORT_PATH}")

            # Self-healing status
            print(f"\n{'=' * 60}")
            print("  Self-Healing Status")
            print(f"{'=' * 60}")

            portfolio_status = _portfolio_enrichment_status()
            if portfolio_status:
                remaining = portfolio_status["remaining_entries"]
                if remaining > 0:
                    print(f"  Portfolio enrichment: {remaining} entries remaining")
                    for fund_info in portfolio_status["top_funds"][:5]:
                        print(f"    {fund_info['slug']}: {fund_info['count']} entries (sector:{fund_info['sector']}, hq:{fund_info['hq']}, desc:{fund_info['desc']})")
                    if len(portfolio_status["top_funds"]) > 5:
                        print(f"    ... +{len(portfolio_status['top_funds']) - 5} more funds")
                else:
                    print(f"  Portfolio enrichment: COMPLETE")
            else:
                print(f"  Portfolio enrichment: COMPLETE")

            if report:
                enriched_info = report.get("enriched", {})
                llm_counts = enriched_info.get("llm_keep_counts") or {}
                none_count = llm_counts.get("none", 0)
                if none_count > 0:
                    print(f"  Signal enrichment: {none_count} signals without decision")
                else:
                    print(f"  Signal enrichment: COMPLETE")

            stp_status = _signal_to_portfolio_status()
            if stp_status:
                if stp_status["remaining"] > 0:
                    print(f"  Signal→Portfolio: {stp_status['remaining']} signals remaining "
                          f"({stp_status['processed']}/{stp_status['total_signals']} done)")
                else:
                    print(f"  Signal→Portfolio: COMPLETE")

            if retry_log:
                print(f"  Auto-retries used: {', '.join(f'{k}={v}' for k, v in retry_log.items())}")
            else:
                print(f"  Auto-retries used: none needed")

            has_remaining = (
                (portfolio_status and portfolio_status.get("remaining_entries", 0) > 0)
                or (report and (report.get("enriched", {}).get("llm_keep_counts") or {}).get("none", 0) > 0)
                or (stp_status and stp_status.get("remaining", 0) > 0)
            )
            if has_remaining:
                print(f"  Pipeline: has remaining work (re-run to continue)")
            else:
                print(f"  Pipeline: fully self-healed")

            # Send Telegram alert with pipeline summary
            _send_pipeline_alert(results, retry_log, step_details, report, total_elapsed)

        print(f"\n  All steps passed.")


if __name__ == "__main__":
    args = sys.argv[1:]
    step_name = None
    dry_run = False
    force_extract = False
    slugs_filter = None

    i = 0
    while i < len(args):
        if args[i] == "--step" and i + 1 < len(args):
            step_name = args[i + 1]
            i += 2
        elif args[i].startswith("--step="):
            step_name = args[i].split("=", 1)[1]
            i += 1
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i] == "--force-extract":
            force_extract = True
            i += 1
        elif args[i] == "--slugs" and i + 1 < len(args):
            slugs_filter = args[i + 1]
            i += 2
        elif args[i].startswith("--slugs="):
            slugs_filter = args[i].split("=", 1)[1]
            i += 1
        else:
            i += 1

    # Pass flags to relevant step commands
    for step in STEPS:
        if step["name"] == "monitor":
            if force_extract:
                step["command"].append("--force-extract")
            if slugs_filter:
                step["command"].extend(["--slugs", slugs_filter])
        elif step["name"] == "enrich_portfolio" and slugs_filter:
            step["command"].extend(["--slugs", slugs_filter])
        elif step["name"] == "enrich" and slugs_filter:
            step["command"].extend(["--slugs", slugs_filter])
        elif step["name"] == "signal_to_portfolio" and slugs_filter:
            step["command"].extend(["--slugs", slugs_filter])

    run_pipeline(only_step=step_name, dry_run=dry_run)
