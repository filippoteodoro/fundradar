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

# ── Model config ──────────────────────────────────────────────────────────────
# Single source of truth for AI model names. Update here when upgrading.
# Do NOT use gemini-2.x models — they hallucinate more for structured data extraction.
# Do NOT use Flash-Lite for portfolio/fund enrichment — it's optimised for throughput,
# not accuracy. Lite quality < Flash quality for fact-extraction tasks.
GEMINI_MODEL = "gemini-3-flash-preview"
# Do NOT use ChatGPT 4o — hallucinates too frequently for structured data tasks.
OPENAI_MODEL = "gpt-5.4-mini"

# ── Canonical sector taxonomy ─────────────────────────────────────────────────
# Single source of truth — used by normalize_sectors.py, signal_to_portfolio.py,
# enrich_portfolio_gemini_full.py, normalize_portfolio_cross_fund.py.
SECTOR_TAXONOMY = [
    "Technology", "Software", "Healthcare", "Biotech & Pharma",
    "Financial Services", "Insurance", "Consumer Goods", "Retail",
    "Food & Beverage", "Industrial Manufacturing", "Automotive",
    "Aerospace & Defense", "Energy", "Renewable Energy",
    "Telecommunications", "Media & Entertainment", "Education",
    "Real Estate", "Construction", "Transportation & Logistics",
    "Agriculture", "Chemicals", "Environmental Services",
    "Professional Services", "Hospitality & Tourism",
    "Fashion & Luxury", "Packaging", "Waste Management",
    "Water & Utilities", "Mining & Metals",
]

# ── Output files ──────────────────────────────────────────────────────────────
SIGNALS_FILE = DATA_DIR / "detected_signals.json"
FILTERED_SIGNALS_FILE = DATA_DIR / "detected_signals_filtered.json"
ENRICHED_SIGNALS_FILE = DATA_DIR / "detected_signals_enriched.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio_items.json"
COMPANY_PROFILES_FILE = DATA_DIR / "company_profiles.json"
