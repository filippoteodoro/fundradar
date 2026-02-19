# Fundradar Worker

Python worker for website scraping, data extraction, change detection, and signal generation.

## Setup

```bash
cd apps/worker
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Playwright Setup (for JS-heavy sites)

```bash
playwright install chromium
```

## Commands

From project root:
```bash
pnpm pipeline              # Full pipeline: monitor → filter → enrich
pnpm pipeline --force-extract  # Re-extract all (use after updating extractors)
pnpm pipeline:signals      # Filter + enrich only (skip fetching)
pnpm worker:monitor        # Fetch websites, extract data, detect changes
pnpm worker:ingest         # Process PEM PDFs → pem_deals.json
pnpm worker:aifi           # Scrape AIFI member data
pnpm worker:geocode        # Geocode fund addresses
```

## Architecture

```
monitor (fetch + extract + diff) → filter (quality scoring) → enrich (AI summaries)
```

`pnpm pipeline` and `pnpm worker:monitor` both use `data/derived/domain_policies.json` automatically for:
- `requires_headless` routing to Playwright
- per-domain Playwright tuning (`playwright_profile`, `playwright_retry_count`, `playwright_random_delay_ms`)
- optional per-domain Playwright proxy (`playwright_proxy`)

### Key Modules

| Module | Purpose |
|--------|---------|
| `monitor.py` | Main fetch/extract/diff engine |
| `pipeline.py` | 3-step orchestration |
| `strategy_orchestrator.py` | Extraction strategy selection |
| `strategies/extractors/` | 160+ fund-specific extractors |
| `fetcher.py` | HTTP fetching with rate limiting |
| `playwright_fetcher.py` | JS-heavy site fetching |
| `differ.py` | Change detection between page versions |
| `enrichment.py` | Fund profile enrichment |
| `noise_filter.py` | Signal quality scoring |
| `domain_policies.py` | Per-domain fetch configuration |
| `io_utils.py` | Atomic file writes, sanitization |

### Playwright Policy Fields (per domain)

```json
{
  "example.com": {
    "requires_headless": true,
    "playwright_profile": "cloudflare",
    "playwright_retry_count": 3,
    "playwright_random_delay_ms": [250, 900],
    "playwright_proxy": {
      "server": "http://proxy.example:8080",
      "username": "user",
      "password": "pass",
      "bypass": ".internal,.local"
    }
  }
}
```

The monitor also detects anti-bot challenge pages and records `bot_challenge` in URL status reports for stronger backoff and triage.

### Extraction Strategy

1. Fund-specific extractor (`strategies/extractors/{fund}.py`) runs first
2. If it returns results, generic strategies are **skipped**
3. If no extractor exists or returns nothing: generic chain runs (NEXT_DATA → JSON_LD → HTML_CARDS → LOGO_GRID)

### Fund-Specific Extractors

Each extractor in `strategies/extractors/` exports:
- `DOMAIN` — the domain it handles
- `URLS` — dict of page paths (`portfolio`, `team`, `news`)
- `EXTRACTORS` — dict mapping data types to extraction functions

## Tests

```bash
cd apps/worker
pytest
```

## See Also

- `CLAUDE.md` in this directory for detailed worker architecture docs
- Root `CLAUDE.md` for project-wide instructions
