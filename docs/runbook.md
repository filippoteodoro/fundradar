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
| `FUNDRADAR_PLAYWRIGHT_PROXY_SERVER` | unset | Global Playwright proxy server (`http://host:port`) |
| `FUNDRADAR_PLAYWRIGHT_PROXY_USERNAME` | unset | Global Playwright proxy username |
| `FUNDRADAR_PLAYWRIGHT_PROXY_PASSWORD` | unset | Global Playwright proxy password |
| `FUNDRADAR_PLAYWRIGHT_PROXY_BYPASS` | unset | Comma-separated bypass list |

### Domain-Specific Configuration

Per-domain settings are in `data/derived/domain_policies.json`:

```json
{
  "www.example.com": {
    "requires_headless": true,
    "ssl_verify": false,
    "rate_limit_delay": 3.0,
    "playwright_profile": "cloudflare",
    "playwright_retry_count": 3,
    "playwright_random_delay_ms": [250, 900],
    "playwright_proxy": {
      "server": "http://proxy.example:8080",
      "username": "user",
      "password": "pass",
      "bypass": ".internal,.local"
    },
    "reason": "JS-rendered SPA"
  }
}
```

Notes:
- These settings are consumed automatically by `pnpm pipeline` and `pnpm worker:monitor` (no extra flags).
- `playwright_profile` supports `default`, `balanced`, `aggressive`, `cloudflare`, `akamai`.
- `playwright_proxy` is per-domain and overrides global proxy env vars.

### Fund-Specific Extractors

Each fund's scraping logic is in `apps/worker/fundradar_worker/strategies/extractors/{fund}.py`. Extractors define:
- `DOMAIN` — which domain they handle
- `URLS` — which page paths to fetch
- `EXTRACTORS` — extraction functions per data type

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

### Rate Limiting / Timeouts

**Fix:** Increase delay in `data/derived/domain_policies.json`:
```json
{ "domain.com": { "rate_limit_delay": 5.0 } }
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

### Bot Protection / WAF Challenges

The monitor now detects common anti-bot pages (Cloudflare/Akamai/CAPTCHA markers) and records URL status as `bot_challenge` with longer backoff.

Suggested workflow:
1. Run `pnpm worker:monitor --slugs fund-slug --force-extract`.
2. Inspect `data/derived/url_status_report.json` and `data/derived/url_status.json`.
3. For repeatedly blocked domains, add per-domain Playwright policy fields (`playwright_profile`, `playwright_retry_count`, optional `playwright_proxy`).

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
