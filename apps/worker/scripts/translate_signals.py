#!/usr/bin/env python3
"""
Pipeline step: Translate non-English signals to English (DeepL → OpenAI fallback).

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
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv, dotenv_values

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "derived"
WORKER_DIR = PROJECT_ROOT / "apps" / "worker"
SIGNALS_FILE = DATA_DIR / "detected_signals.json"

# ── Environment ────────────────────────────────────────────────────────────────

ENV_PATH = WORKER_DIR / ".env"
load_dotenv(ENV_PATH, override=False)
if ENV_PATH.exists():
    env_vars = dotenv_values(ENV_PATH)
    for key in ("OPENAI_API_KEY", "DEEPL_API_KEY", "DEEPL_API_KEY_2", "AZURE_TRANSLATOR_KEY", "AZURE_TRANSLATOR_REGION"):
        if not os.environ.get(key) and env_vars.get(key):
            os.environ[key] = env_vars[key]

# ── Import translator ──────────────────────────────────────────────────────────

from fundradar_worker.translator import translate_signals_inplace


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_signals() -> dict:
    if not SIGNALS_FILE.exists():
        return {"signals": []}
    with open(SIGNALS_FILE) as f:
        return json.load(f)


def _save_signals(data: dict) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, str(SIGNALS_FILE))
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate non-English signals to English")
    parser.add_argument(
        "--slugs",
        default=None,
        help="Comma-separated fund slugs to translate (default: all)",
    )
    args = parser.parse_args()
    slugs_filter = args.slugs

    print(f"\n{'=' * 60}")
    print("  Translation step: non-English → English")
    if slugs_filter:
        print(f"  Scope: {slugs_filter}")
    print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 60}")

    data = _load_signals()
    signals: list[dict] = data.get("signals", [])

    if not signals:
        print("  No signals found — nothing to translate")
        sys.exit(0)

    # Apply slugs filter if requested
    if slugs_filter:
        target_slugs = {s.strip() for s in slugs_filter.split(",")}
        signals_to_translate = [s for s in signals if s.get("fund_slug") in target_slugs]
        print(f"  Signals for requested slugs: {len(signals_to_translate)} / {len(signals)} total")
    else:
        signals_to_translate = signals

    if not signals_to_translate:
        print("  No signals for the requested slugs — done")
        sys.exit(0)

    stats = translate_signals_inplace(
        signals_to_translate,
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        slugs_filter=slugs_filter,
    )

    # Persist the updated signals (even if zero translated — idempotent write is fine)
    data["signals"] = signals  # list was modified in-place
    data["translated_at"] = datetime.now(timezone.utc).isoformat()
    _save_signals(data)

    detected = stats.get("italian_fields_detected", 0)
    translated = stats.get("translated_fields", 0)
    unresolved = stats.get("unresolved_fields", 0)
    skip_reason = stats.get("skipped_reason", "")

    print(f"\n  Results:")
    print(f"    Non-English fields detected: {detected}")
    print(f"    Translated fields:           {translated}")
    if unresolved:
        print(f"    Unresolved fields:           {unresolved}")
    if skip_reason:
        print(f"    Skipped reason:              {skip_reason}")
    print(f"\n  Saved: {SIGNALS_FILE}")

    # Exit code 1 if ALL fields were unresolved (no provider available)
    if skip_reason == "no_provider" and detected > 0:
        print("  WARNING: no translation provider configured — signals remain in original language")
        sys.exit(1)


if __name__ == "__main__":
    main()
