# Fundradar Worker

Python worker for website scraping, data extraction, change detection and signal processing.

## Setup

```bash
cd apps/worker
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # add ",ml" for the optional signal classifier
playwright install chromium
```

API keys go in `apps/worker/.env`. The key list is in the root [README](../../README.md#api-keys-pipeline-only). Other settings are in [`docs/runbook.md`](../../docs/runbook.md#configuration).

## Commands

From the repo root:
```bash
pnpm pipeline                  # Full 10-step pipeline
pnpm pipeline --force-extract  # Re-extract all (use after updating extractors)
pnpm pipeline:signals          # Filter + enrich only (no fetching)
pnpm worker:monitor            # Fetch websites, extract data, detect changes
pnpm worker:ingest             # Process PEM PDFs → pem_deals.json (needs local PDFs in data/pem/)
pnpm worker:aifi               # Scrape AIFI member data
pnpm worker:geocode            # Geocode fund addresses
```

The root commands activate `apps/worker/.venv` themselves.

## Architecture

```
monitor → rss → translate → normalize_sectors → normalize_portfolio → enrich_portfolio
        → filter → enrich → signal_to_portfolio → enrich_portfolio_final
```

The step list is `STEPS` in `fundradar_worker/pipeline.py`. [`CLAUDE.md`](./CLAUDE.md) describes each step.

### Key Modules

| Module | Purpose |
|--------|---------|
| `monitor.py` | Main fetch/extract/diff engine |
| `pipeline.py` | Pipeline orchestration |
| `strategy_orchestrator.py` | Extraction strategy selection |
| `strategies/extractors/` | Fund-specific extractors |
| `fetcher.py` | HTTP fetching with rate limiting |
| `playwright_fetcher.py` | JS-heavy site fetching |
| `differ.py` | Change detection between page versions |
| `enrichment.py` | Fund profile enrichment |
| `noise_filter.py` | Signal quality scoring |
| `domain_policies.py` | Per-domain fetch configuration |
| `io_utils.py` | Atomic file writes, sanitization |

### Extraction Strategy

1. The fund-specific extractor (`strategies/extractors/{fund}.py`) runs first.
2. If it returns results, generic strategies are **skipped**.
3. If no extractor exists or it returns nothing, the generic chain runs (NEXT_DATA → JSON_LD → HTML_CARDS → LOGO_GRID).

Each extractor exports `DOMAIN`, `URLS` (page paths for `portfolio`, `team`, `news`) and `EXTRACTORS` (data type → function). Bot-protected domains get extractor-level URL routing; see [`docs/runbook.md`](../../docs/runbook.md#bot-protected-domain-keeps-returning-403).

## Tests

```bash
cd apps/worker
pytest
```

## See Also

- [`CLAUDE.md`](./CLAUDE.md) in this directory for detailed worker notes
- Root [`AGENTS.md`](../../AGENTS.md) for project-wide rules
- [`docs/ADDING_A_FUND.md`](../../docs/ADDING_A_FUND.md) to add a fund
