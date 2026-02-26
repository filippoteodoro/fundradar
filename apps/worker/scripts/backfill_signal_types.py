#!/usr/bin/env python3
"""One-time backfill: populate signal_types on existing filtered + enriched JSON.

Free — no API calls. Safe to re-run (idempotent: skips signals that already
have signal_types set).

Usage:
    cd apps/worker
    python scripts/backfill_signal_types.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow importing from scripts/ and fundradar_worker/
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from signal_corrections import detect_all_signal_types
from fundradar_worker.io_utils import safe_json_write
from fundradar_worker.paths import DATA_DIR


def backfill(path: Path) -> None:
    if not path.exists():
        print(f"  SKIP (file not found): {path.name}")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    signals = data.get("signals", [])
    patched = 0
    for sig in signals:
        if not sig.get("signal_types"):
            sig["signal_types"] = detect_all_signal_types(sig)
            patched += 1
    safe_json_write(path, data)
    print(f"  {path.name}: patched {patched}/{len(signals)} signals")


if __name__ == "__main__":
    print("Backfilling signal_types ...")
    backfill(DATA_DIR / "detected_signals_filtered.json")
    backfill(DATA_DIR / "detected_signals_enriched.json")
    print("Done.")
