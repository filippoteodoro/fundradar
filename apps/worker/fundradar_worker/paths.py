"""
Shared path constants for the FundRadar worker pipeline.

This is the SINGLE source of truth for project paths. All pipeline scripts
should import from here instead of computing paths via Path(__file__).parent...

Usage:
    from fundradar_worker.paths import PROJECT_ROOT, DATA_DIR, DB_PATH
"""

from pathlib import Path

# ── Project structure ─────────────────────────────────────────────────────────
# fundradar_worker/ is at apps/worker/fundradar_worker/
# So PROJECT_ROOT is 3 levels up from this file.
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

WORKER_DIR = PROJECT_ROOT / "apps" / "worker"
SCRIPTS_DIR = WORKER_DIR / "scripts"

# ── Data paths ────────────────────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data" / "derived"
DB_PATH = PROJECT_ROOT / "data" / "db.json"

# ── Environment ───────────────────────────────────────────────────────────────
# Root .env has all keys; worker .env may have overrides.
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
WORKER_ENV_PATH = WORKER_DIR / ".env"

# ── Output files ──────────────────────────────────────────────────────────────
SIGNALS_FILE = DATA_DIR / "detected_signals.json"
FILTERED_SIGNALS_FILE = DATA_DIR / "detected_signals_filtered.json"
ENRICHED_SIGNALS_FILE = DATA_DIR / "detected_signals_enriched.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio_items.json"
