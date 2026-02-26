# Fundradar Worker Production Runbook

Operations and troubleshooting for the Fundradar scraping worker.

For legal/compliance operations, use:
- `docs/compliance-dsar-runbook.md`
- `docs/compliance-incident-response.md`
- `docs/compliance-processor-register.md`

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
- `arca-space-capital` now has routed team/news coverage on Space Capital:
  - `team`: `https://www.spacecapital.it/it/investment-team.html`, `https://www.spacecapital.it/it/industry-specialist.html`
  - `news`: `https://www.spacecapital.it/it/news/index.html`, `https://www.spacecapital.it/en/news/index.html`
  - extractor now includes a custom `news` parser (module-card + fallback link extraction)
- `hat-sicaf` no longer relies on iframe wrapper HTML:
  - monitored URLs remain on `www.hatsicaf.it` for correct slug mapping
  - extractor resolves underlying `hat.it` pages for `portfolio`, `team`, and `news`
  - module sets `ALWAYS_EXTRACT = True` because wrapper HTML is mostly static
  - parser uses live target fetch first, then local snapshot cache fallback
- `quattror` now has custom `team` and `news` extraction from structured cards:
  - `team`: parses `People` cards (`article.str__article`) including role mapping and photos
  - `news`: parses newsroom cards with title/date/summary and press-PDF URL fallback
  - portfolio parsing is now scoped to portfolio-card links (avoids accidental team/news misreads)
- `merito-sgr` now has extractor-native API routing plus popup-team parsing:
  - monitored URLs stay on canonical pages with stable cache-buster params (`/investimenti/?fr_src=fundradar`, `/team/?fr_src=fundradar`, `/news/?fr_src=fundradar`) to avoid stale `304` loops without cached blobs
  - extractor attempts WordPress JSON fallback (`/wp-json/wp/v2/posts?...`) for `portfolio` and `news` when HTML shell pages are empty
  - `team`: parses popup cards (`.paoc-cb-popup-body`) for name/title/photo with role mapping
  - module sets `ALWAYS_EXTRACT = True` so API-backed pages are re-extracted even when HTML wrappers are unchanged
- `faro-value` URL routing was corrected from stale 404 paths:
  - `team`: `/about-us/` (replaces `/management`)
  - `news`: `/media-events/` (replaces `/en/news`)
- `teamsystem-capital-at-work-sgr` URL routing was corrected from stale 404 paths:
  - `team`: `/it/team` (replaces `/it/management`)
  - `news`: `/it/stampa` (replaces `/it/en/news`)
- `ream-sgr` now has extractor URL routing enabled (was effectively disabled with all paths `None`):
  - `portfolio`: routed to fund-category pages (`/i-fondi-ream/core.html`, `/residenziale.html`, `/etico.html`, `/sanitario.html`, `/rigenerazione-urbana.html`)
  - `team`: `/la-societa/chi-siamo-ream.html`
  - `news`: `/comunicazione/comunicati-e-notizie.html`
- `finint-investments-sgr` URL routing was corrected from stale 404 paths:
  - `team`: `/it/chi-siamo/management-team.php`, `/it/chi-siamo/storia.php` (replaces `/management`)
  - `news`: `/it/press/comunicati-stampa.php` (replaces missing news URL)
  - team extractor now normalizes all-caps names so members are not dropped by shared team post-processing
- `scientifica-vc` now has full URL routing enabled:
  - `team`: `/team/?fr_src=fundradar`
  - `news`: `/media-ed-eventi/?fr_src=fundradar`
  - `news` extractor now includes HTML-card parsing with WordPress API fallback (`/wp-json/wp/v2/posts`)
- `wrm-group` now monitors media/news directly:
  - `news`: `/media/?fr_src=fundradar` (wired to existing `extract_news`)
- `vertis-sgr` team extraction was upgraded for the current WordPress card layout:
  - parses `.team-l-info` cards (`.text-lead` name + `.text-small` role/title + photo)
  - keeps legacy `<strong>` parsing as fallback for older page variants

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
- `sagitta-sgr` (news via direct newsroom URL `/en/newsroom/`, not RSS)

### Actionable Signal Dropped by Filter

If a recent, Italy-relevant signal is missing from `detected_signals_filtered.json`, re-run:

```bash
pnpm pipeline --step filter
```

Current strict-type recovery rules include:
- Creditor/debt-restructuring signals with explicit tagged-fund mention → `debt_financing`
- "New/additional contributions to <fund>" signals → `fundraise_announced`

Signal text normalization now also repairs merged-token artifacts systemically
(e.g. `€62Mof`, `€3.3Mper`, `agreementfor`, `partnershipwith`,
`diMarulloper`, `TechNovaper`) during `filter`, with entity-aware company token
deconcatenation. Fixes then propagate to `enrich` outputs on the next run.

### Duplicate NEWS Signal Variants in Raw Store

If `data/derived/detected_signals.json` shows near-duplicate NEWS rows for the same
article (for example old malformed text and a later corrected variant), run:

```bash
python -m fundradar_worker.monitor --slugs fund-slug --force-extract --skip-backoff
```

`SignalStore` now coalesces NEWS duplicates by stable identity
(`fund_slug + source_url + title + published_at`) and keeps the better/newer
variant, so corrected re-extractions replace stale malformed entries.

### Multi-fund tagging in `/signals`

Expected behavior:
- A single signal card can show multiple blue fund links in the header.
- The same signal should appear on each tagged fund page without duplicating cards in `/signals`.

How it works:
- RSS monitor emits `related_fund_slugs` for each signal when multiple funds are involved.
- Web loaders keep backward compatibility by inferring extra fund tags from signal text for older rows.
- Both layers suppress speculative-only candidate mentions (for example `among interested bidders`,
  `in the running`, `fra/tra gli interessati`) so passive rumor mentions do not become related fund tags.
- RSS guard behavior: when at least one non-speculative active slug exists in an article, speculative-only
  candidates are dropped from `related_fund_slugs`; pure-rumor articles (all slugs speculative) are preserved.

Validation:
```bash
python - <<'PY'
import json
from pathlib import Path
p=Path("data/derived/detected_signals_enriched.json")
if not p.exists(): p=Path("data/derived/detected_signals_filtered.json")
s=json.loads(p.read_text()).get("signals", [])
print(sum(1 for x in s if isinstance(x.get("related_fund_slugs"), list) and len(x["related_fund_slugs"])>1))
PY
```

Note: this checks persisted `related_fund_slugs` written by worker runs. The web layer
also infers extra tags for legacy rows that predate this field.

### Translation Failures (IT→EN)

`enrich_signals_openai.py` now sends a Telegram alert when Italian fields are
detected but translation is blocked/partial (e.g., DeepL/OpenAI DNS/connectivity
errors, missing API keys).

Required env vars for Telegram delivery:
- `FUNDRADAR_TELEGRAM_BOT_TOKEN`
- `FUNDRADAR_TELEGRAM_CHAT_ID`

Optional toggle:
- `SIGNAL_TRANSLATION_ALERTS=1` (default on; set `0` to disable)
- `SIGNAL_ENRICH_STRICT_NETWORK=1` (default on):
  - when DNS/API connectivity degrades during enrich, script exits with code `2`
  - pipeline auto-retries and records a step warning instead of silently passing

Latest network health status is persisted to:
- `data/derived/signal_enrichment_network_status.json`

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
