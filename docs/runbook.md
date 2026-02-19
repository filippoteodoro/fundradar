# Fundradar Worker Production Runbook

Operations and troubleshooting for the Fundradar scraping worker.

## Prerequisites

- Python 3.11+
- Playwright (`playwright install chromium`)
- pnpm (monorepo commands)

## Running the Pipeline

### Full Pipeline (fetch + filter + enrich)

```bash
pnpm pipeline
```

### Re-extract after updating extractors

```bash
pnpm pipeline --force-extract
```

### Specific funds only

```bash
pnpm pipeline --slugs investindustrial,permira --force-extract
```

### Enrich signals for specific funds only

```bash
pnpm pipeline --step enrich --slugs sagitta-sgr,carlyle
```

This performs slug-scoped signal enrichment and preserves non-target rows in
`data/derived/detected_signals_enriched.json`.

### Filter + enrich only (skip fetching)

```bash
pnpm pipeline:signals
```

### One-off fund scrape

```bash
python -m fundradar_worker.cli scrape-fund investindustrial
python -m fundradar_worker.cli scrape-fund investindustrial --dry-run
python -m fundradar_worker.cli scrape-fund investindustrial --force
```

### Monitor with options

```bash
python -m fundradar_worker.monitor --limit 10
python -m fundradar_worker.monitor --skip-backoff
python -m fundradar_worker.monitor --force-extract
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FUNDRADAR_LOG_LEVEL` | `INFO` | Log level |
| `FUNDRADAR_MAX_CONCURRENT` | `3` | Max concurrent browser contexts |
| `FUNDRADAR_RATE_LIMIT_DEFAULT` | `2.0` | Seconds between requests to same domain |
| `FUNDRADAR_REQUEST_TIMEOUT` | `30` | Request timeout in seconds |
| `FUNDRADAR_CIRCUIT_FAILURE_THRESHOLD` | `5` | Failures before circuit opens |
| `FUNDRADAR_CIRCUIT_COOLDOWN` | `300` | Seconds before circuit half-opens |
| `PLAYWRIGHT_HEADLESS` | `true` | Run browsers in headless mode |

### Domain-Specific Configuration

Per-domain settings are in `data/derived/domain_policies.json`:

```json
{
  "www.example.com": {
    "requires_headless": true,
    "ssl_verify": false,
    "rate_limit_seconds": 3.0,
    "reason": "JS-rendered SPA"
  }
}
```

### Fund-Specific Extractors

Each fund's scraping logic is in `apps/worker/fundradar_worker/strategies/extractors/{fund}.py`. Extractors define:
- `DOMAIN` — which domain they handle
- `URLS` — which page paths to fetch
- `EXTRACTORS` — extraction functions per data type

Recent fund-specific update:
- `yarpa-investimenti-sgr` now has custom `team` and `news` extractors with:
  - `team`: `https://www.yarpa.it/le-persone/`
  - `news`: `https://www.yarpa.it/press/`
  - `portfolio`: intentionally `None` (fund-of-funds model, no company-level portfolio page)
- `eiffel` now has custom Frontity-state `team` and `news` extractors with:
  - `team`: `https://www.eiffel-ig.com/en/group/team/`, `https://www.eiffel-ig.com/groupe/equipe/`
  - `news`: `https://www.eiffel-ig.com/en/news/`, `https://www.eiffel-ig.com/actualites/`
  - extractor reads embedded `__FRONTITY_CONNECT_STATE__` JSON (works even when content is JS-app rendered)
  - `portfolio`: intentionally `None` (no stable public company-level portfolio grid)

## Monitoring

### Health Report

```bash
python -m fundradar_worker.cli health-report --verbose
python -m fundradar_worker.cli health-report --json
```

### Circuit Breaker Status

```bash
python -m fundradar_worker.cli list-errors
python -m fundradar_worker.cli list-errors --status open
```

### Key Files

| File | Purpose |
|------|---------|
| `data/derived/detected_signals.json` | Raw generated signals |
| `data/derived/detected_signals_filtered.json` | Quality-filtered signals |
| `data/derived/portfolio_items.json` | Extracted portfolio companies |
| `data/derived/url_status.json` | URL health tracking |
| `data/derived/circuit_state.json` | Circuit breaker state |
| `data/derived/url_status_report.json` | Domain status report |

## Troubleshooting

### Circuit Breaker Open

**Symptom:** "Circuit open for domain.com"

```bash
# Check which domains are failing
python -m fundradar_worker.cli list-errors --status open

# Reset a specific domain
python -m fundradar_worker.cli reset-backoff domain.com

# Reset all
python -m fundradar_worker.cli reset-backoff --all
```

### JS-Heavy Site Returns Empty Content

**Fix:**
1. Verify Playwright is installed: `playwright install chromium`
2. Add headless requirement to `data/derived/domain_policies.json`:
   ```json
   { "domain.com": { "requires_headless": true } }
   ```
3. Re-run: `pnpm pipeline --slugs fund-slug --force-extract`

### Bot-Protected Domain Keeps Returning 403

When a fund domain blocks top-level pages, prefer extractor-level endpoint routing
instead of monitor/pipeline changes:
1. Update the fund extractor `URLS` in `apps/worker/fundradar_worker/strategies/extractors/{fund}.py`
2. Route to deeper endpoints (portfolio detail, newsroom, press archive), public APIs, or scoped RSS fallback feeds when the official site is fully blocked
3. Add extractor fallback parsing for detail pages / JSON payloads
4. Re-run only that fund with force extract:
   ```bash
   pnpm pipeline --slugs fund-slug --force-extract
   ```

Current extractor-routed blocked funds:
- `algebris` (news via scoped RSS fallback)
- `capital-dynamics-sgr` (news via scoped RSS fallback)
- `carlyle`
- `oxy-capital`
- `sagitta-sgr`

### Actionable Signal Dropped by Filter

If a recent, Italy-relevant signal is missing from `detected_signals_filtered.json`, re-run:

```bash
pnpm pipeline --step filter
```

Current strict-type recovery rules include:
- Creditor/debt-restructuring signals with explicit tagged-fund mention → `debt_financing`
- "New/additional contributions to <fund>" signals → `fundraise_announced`

### Rate Limiting / Timeouts

**Fix:** Increase delay in `data/derived/domain_policies.json`:
```json
{ "domain.com": { "rate_limit_seconds": 5.0 } }
```

### SSL Certificate Errors

**Fix:** Disable SSL verification in `data/derived/domain_policies.json`:
```json
{ "domain.com": { "ssl_verify": false } }
```

### 304 Not Modified + --force-extract

When a server returns 304 Not Modified, `--force-extract` loads cached HTML from blob storage (`data/derived/blobs/{hash}.html`) and re-extracts. If no cached blob exists, extraction is skipped for that URL.

### PortfolioStore Safety Guard

If extraction returns significantly fewer entries than before (< 50% of previous count), the update is blocked to prevent data loss. To bypass:
1. Clear the fund's entries from `portfolio_items.json`
2. Re-run pipeline with `--force-extract`

### Web UI Shows Stale Data

Data is cached in-memory with no TTL. After any worker run, restart `pnpm dev`.

## Common Operations

### Reset All Circuit Breakers

```bash
python -m fundradar_worker.cli reset-backoff --all
```

### Regression Testing

```bash
python -m fundradar_worker.cli generate-baselines --overwrite
python -m fundradar_worker.cli check-regression
```

### Force Re-Extract All Sites

```bash
pnpm pipeline --force-extract
```

### Backup Data

```bash
tar -czvf fundradar-backup-$(date +%Y%m%d).tar.gz data/derived/
```

### Graceful Shutdown

The worker handles SIGTERM/SIGINT gracefully — completes current URL, saves checkpoint.
