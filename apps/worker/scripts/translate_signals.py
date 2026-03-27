#!/usr/bin/env python3
"""
Pipeline step: Translate non-English signals to English (DeepL → Azure fallback).

Runs between the rss step and the filter step so that:
  - filter_signals.py receives English text → correct keyword classification
  - enrich_signals_openai.py receives English text → better summaries, no re-translation

Reads:  data/derived/detected_signals.json
Writes: data/derived/detected_signals.json  (in-place, with *_original fields preserved)

Idempotent: already-translated signals are skipped (checks *_original fields).

Usage:
    python apps/worker/scripts/translate_signals.py
    python apps/worker/scripts/translate_signals.py --slugs f2i-sgr,ardian
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from typing import Any

from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────

WORKER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(WORKER_DIR))

from fundradar_worker.paths import PROJECT_ROOT, DATA_DIR, SIGNALS_FILE, WORKER_ENV_PATH as ENV_PATH
from fundradar_worker.io_utils import safe_json_write

# ── Timeout ────────────────────────────────────────────────────────────────────

from fundradar_worker.graceful_deadline import GracefulDeadline
_deadline = GracefulDeadline(deadline_seconds=8 * 60, env_var="TRANSLATE_DEADLINE_SECONDS")
TRANSLATE_DEADLINE_SECONDS = _deadline.deadline_seconds


# ── Environment ────────────────────────────────────────────────────────────────
load_dotenv(ENV_PATH, override=False)

# ── Import translator ──────────────────────────────────────────────────────────

from fundradar_worker.translator import translate_signals_inplace


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_signals() -> dict:
    if not SIGNALS_FILE.exists():
        return {"signals": []}
    with open(SIGNALS_FILE) as f:
        return json.load(f)


def _save_signals(data: dict) -> None:
    safe_json_write(SIGNALS_FILE, data)


def main() -> None:
    _deadline.install_signals()
    _deadline.start()

    parser = argparse.ArgumentParser(description="Translate non-English signals to English")
    parser.add_argument(
        "--slugs",
        default=None,
        help="Comma-separated fund slugs to translate (default: all)",
    )
    args = parser.parse_args()
    slugs_filter = args.slugs

    print(f"\n{'=' * 60}", flush=True)
    print("  Translation step: non-English → English", flush=True)
    if slugs_filter:
        print(f"  Scope: {slugs_filter}", flush=True)
    print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", flush=True)
    print(f"  Deadline: {TRANSLATE_DEADLINE_SECONDS}s ({TRANSLATE_DEADLINE_SECONDS // 60}m)", flush=True)
    print(f"{'=' * 60}", flush=True)

    data = _load_signals()
    signals: list[dict] = data.get("signals", [])

    if not signals:
        print("  No signals found — nothing to translate", flush=True)
        sys.exit(0)

    # Apply slugs filter if requested
    if slugs_filter:
        target_slugs = {s.strip() for s in slugs_filter.split(",")}
        signals_to_translate = [s for s in signals if s.get("fund_slug") in target_slugs]
        print(f"  Signals for requested slugs: {len(signals_to_translate)} / {len(signals)} total", flush=True)
    else:
        signals_to_translate = signals

    if not signals_to_translate:
        print("  No signals for the requested slugs — done", flush=True)
        sys.exit(0)

    # Run translation in a daemon thread with deadline timeout
    _result: list[dict[str, Any]] = [{}]

    def _run():
        try:
            _result[0] = translate_signals_inplace(
                signals_to_translate,
                azure_translator_key=os.environ.get("AZURE_TRANSLATOR_KEY"),
                azure_translator_region=os.environ.get("AZURE_TRANSLATOR_REGION"),
                slugs_filter=slugs_filter,
            )
        except Exception as e:
            print(f"  Translation error: {e}", flush=True)
            _result[0] = {"skipped_reason": f"error: {str(e)[:200]}"}

    t = Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=TRANSLATE_DEADLINE_SECONDS)

    if t.is_alive():
        elapsed = _deadline.elapsed()
        print(f"\n  Translation TIMEOUT after {elapsed:.0f}s (limit: {TRANSLATE_DEADLINE_SECONDS}s)", flush=True)
        print("  Saving partially translated signals...", flush=True)
        stats = {"skipped_reason": f"timeout_after_{elapsed:.0f}s"}
    else:
        stats = _result[0]

    # Persist the updated signals (even if partial — better than nothing)
    data["signals"] = signals  # list was modified in-place
    data["translated_at"] = datetime.now(timezone.utc).isoformat()
    _save_signals(data)

    detected = stats.get("italian_fields_detected", 0)
    translated = stats.get("translated_fields", 0)
    unresolved = stats.get("unresolved_fields", 0)
    skip_reason = stats.get("skipped_reason", "")

    elapsed = _deadline.elapsed()
    print(f"\n  Results ({elapsed:.0f}s):", flush=True)
    print(f"    Non-English fields detected: {detected}", flush=True)
    print(f"    Translated fields:           {translated}", flush=True)
    if unresolved:
        print(f"    Unresolved fields:           {unresolved}", flush=True)
    if skip_reason:
        print(f"    Skipped reason:              {skip_reason}", flush=True)
    print(f"\n  Saved: {SIGNALS_FILE}", flush=True)

    # Exit code 1 if ALL fields were unresolved (no provider available)
    if skip_reason == "no_provider" and detected > 0:
        print("  WARNING: no translation provider configured — signals remain in original language", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
