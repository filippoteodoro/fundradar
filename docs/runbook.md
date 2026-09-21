# Fundradar Worker Runbook

Operations and troubleshooting for the Fundradar worker.

## Prerequisites

- Python 3.10+ (CI uses 3.11)
- Node.js 20 and pnpm 9 (monorepo commands)
- Playwright (`playwright install chromium`)
- API keys in `apps/worker/.env` (list: root `README.md` → "API keys")

## Running the Pipeline

### Full Pipeline (fetch + filter + enrich)

```bash
pnpm pipeline
```

Run it from the repo root. The root `pnpm` worker commands activate `apps/worker/.venv` themselves.

The pipeline runs a preflight before any API spend. Treat a preflight failure as an environment or storage problem first, not as a scraper regression.

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

Run these from `apps/worker` with the venv active:

```bash
python -m fundradar_worker.monitor --limit 10
python -m fundradar_worker.monitor --slugs fund-slug
python -m fundradar_worker.monitor --skip-backoff
python -m fundradar_worker.monitor --force-extract
```

`--limit` applies before `--slugs`. Do not combine them, or the target fund can drop out.

## Configuration

### Environment Variables

API keys are listed in the root `README.md`. The code also reads these settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `FUNDRADAR_MAX_WORKERS` | `8` | Parallel domain workers in the monitor |
| `FUNDRADAR_MAX_TOTAL_TIMEOUT` | `3600` | Upper limit in seconds for the monitor batch timeout |
| `FUNDRADAR_RATE_LIMIT_DEFAULT` | `2.0` | Seconds between requests to the same domain |
| `FUNDRADAR_GLOBAL_RATE_LIMIT` | `120` | Max requests per minute across all domains |
| `FUNDRADAR_CIRCUIT_FAILURE_THRESHOLD` | `5` | Failures before the circuit opens |
| `FUNDRADAR_CIRCUIT_COOLDOWN` | `300` | Seconds before the circuit half-opens |
| `FUNDRADAR_SHUTDOWN_TIMEOUT` | `30` | Seconds to wait for a graceful shutdown |
| `PLAYWRIGHT_HEADLESS` | headless | Set `false` to show the browser |
| `SIGNAL_MIN_QUALITY` | `80` | Filter quality threshold |
| `FUNDRADAR_TELEGRAM_BOT_TOKEN`, `FUNDRADAR_TELEGRAM_CHAT_ID` | empty | Optional Telegram alerts; empty disables them |
| `FUNDRADAR_ALERT_WEBHOOK` | empty | Optional webhook for alerts |

### Domain-Specific Configuration

Per-domain settings are in `data/derived/domain_policies.json`. The file is gitignored; create it when you need an override:

```json
{
  "policies": {
    "www.example.com": {
      "requires_headless": true,
      "ssl_verify": false,
      "rate_limit_delay": 3.0,
      "timeout": 60,
      "reason": "JS-rendered SPA"
    }
  }
}
```

Other keys: `retry_count`, `skip_monitoring`. A lookup tries the domain with and without `www.`.

### Fund-Specific Extractors

Each fund's scraping logic is in `apps/worker/fundradar_worker/strategies/extractors/{fund}.py`. Extractors define:
- `DOMAIN` — which domain they handle
- `URLS` — which page paths to fetch
- `EXTRACTORS` — extraction functions per data type

Fund-specific extractor notes (examples of routing patterns; the extractor files are the source of truth):
- `yarpa-investimenti-sgr`: custom `team`/`news` extractors; `portfolio` is `None` (fund-of-funds, no company-level portfolio page)
  - `team`: `https://www.yarpa.it/le-persone/`; `news`: `https://www.yarpa.it/press/`
- `eiffel`: reads embedded `__FRONTITY_CONNECT_STATE__` JSON (JS-app rendered); `portfolio` is `None` (no stable public portfolio grid)
  - `team`: `https://www.eiffel-ig.com/en/group/team/`, `https://www.eiffel-ig.com/groupe/equipe/`
  - `news`: `https://www.eiffel-ig.com/en/news/`, `https://www.eiffel-ig.com/actualites/`
- `arca-space-capital`: routed to Space Capital pages; custom `news` parser (module-card + fallback link extraction)
  - `team`: `https://www.spacecapital.it/it/investment-team.html`, `https://www.spacecapital.it/it/industry-specialist.html`
  - `news`: `https://www.spacecapital.it/it/news/index.html`, `https://www.spacecapital.it/en/news/index.html`
- `hat-sicaf`: monitored URLs on `www.hatsicaf.it` for slug mapping; extractor resolves underlying `hat.it` pages; `ALWAYS_EXTRACT = True` (wrapper HTML is mostly static); live fetch first, local snapshot cache fallback
- `quattror`: `team` parses `People` cards (`article.str__article`); `news` parses newsroom cards with press-PDF fallback; portfolio scoped to portfolio-card links
- `merito-sgr`: uses stable cache-buster params to avoid stale `304` loops; WordPress JSON fallback (`/wp-json/wp/v2/posts?...`) for portfolio/news when HTML shells are empty; `team` parses popup cards (`.paoc-cb-popup-body`); `ALWAYS_EXTRACT = True`
- `faro-value`: `team`: `/about-us/`; `news`: `/media-events/`
- `teamsystem-capital-at-work-sgr`: `team`: `/it/team`; `news`: `/it/stampa`
- `ream-sgr`: `portfolio` routed to fund-category pages (`/i-fondi-ream/core.html`, `/residenziale.html`, `/etico.html`, `/sanitario.html`, `/rigenerazione-urbana.html`); `team`: `/la-societa/chi-siamo-ream.html`; `news`: `/comunicazione/comunicati-e-notizie.html`
- `finint-investments-sgr`: `team`: `/it/chi-siamo/management-team.php`, `/it/chi-siamo/storia.php`; `news`: `/it/press/comunicati-stampa.php`; team extractor normalizes all-caps names
- `scientifica-vc`: `team`: `/team/?fr_src=fundradar`; `news`: `/media-ed-eventi/?fr_src=fundradar`; HTML-card parsing with WordPress API fallback
- `wrm-group`: `news`: `/media/?fr_src=fundradar`
- `vertis-sgr`: `team` parses `.team-l-info` cards (`.text-lead` name + `.text-small` role); legacy `<strong>` parsing as fallback

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
   { "policies": { "domain.com": { "requires_headless": true } } }
   ```
3. Re-run: `pnpm pipeline --slugs fund-slug --force-extract`

If Playwright asks to install browsers again after it worked before, a disk-cleaner tool may have deleted the Playwright browser cache. Run `playwright install chromium` again.

### Preflight Blocks Before Pipeline Starts

**Symptom:** Pipeline exits before step execution with warnings about low free disk, missing canonical outputs, or file-sync artifacts.

**Fix:**
1. Free disk space first if the warning mentions critically low space.
2. Check `data/derived/` for sync placeholders (`.icloud`) or numbered copies (`name 2.json`). Do not change output paths.
3. Move conflict copies out of the repo and keep the canonical filename in place.
4. Re-run `pnpm pipeline` only after the preflight warnings are resolved.

The preflight is intentionally conservative. It is cheaper to stop than to spend API calls while `data/derived/` or the worker environment is in an unsafe state.

### Global Monitor Timeout / `STUCK:` Domains

The monitor batch timeout is dynamic and based on domain waves plus per-domain sequential work. If it fires, the monitor stops scheduling more domain URLs, cancels queued domain tasks, and gives in-flight fetches one per-URL timeout window to drain before cleanup.

If this warning still appears repeatedly:
1. Treat it as a real slow or stuck domain, not as an output-path issue.
2. Check the listed domains first for bot protection, broken pages, or JS-heavy pages that should be routed more narrowly in the extractor.
3. Only raise the timeout after confirming the domain behavior is legitimate and the extractor URL set is correct.

### `data/db.json` Changes During Worker Recovery

`data/db.json` is the curated fund directory, not disposable worker output. Normal worker recovery should not require broad `db.json` rewrites.

If a pipeline or recovery session leaves `data/db.json` with a large unrelated diff:
1. Review the diff separately from `data/derived/` changes.
2. If the change is a bulk rewrite you cannot justify, restore `data/db.json` from git.
3. Do not bundle unrelated `db.json` drift into a pipeline recovery commit.

### Recover Committed Derived Data Before Re-Spending APIs

If committed derived files in `data/derived/` look degraded locally, prefer git recovery over historical reruns.

Use this pattern:
1. Compare the suspicious files against git first (`portfolio_items.json`, `company_profiles.json`, `detected_signals_filtered.json`, `detected_signals_enriched.json`, `signal_enrichment_progress.json`).
2. Restore the last good committed version of the degraded artifact from git.
3. Keep committed progress trackers unless you have proof they are wrong. In particular, do not delete `signal_enrichment_progress.json`.
4. Replay only the minimal current work after the restore:
   - `pnpm pipeline:signals-to-portfolio` for free local portfolio sync
   - targeted `pnpm pipeline --step filter` / `--step enrich` only if today's new signals truly need regeneration
5. Treat a sudden backlog explosion as a recovery symptom first, not as evidence that months of API work genuinely disappeared.

This is usually cheaper and safer than rerunning historical OpenAI or Gemini enrichment.

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

Extractor-routed blocked funds (check the extractor files for the current routing):
- `algebris` (news via scoped RSS fallback)
- `capital-dynamics-sgr` (news via scoped RSS fallback)
- `carlyle`
- `oxy-capital`
- `sagitta-sgr` (news via direct newsroom URL `/en/newsroom/`, not RSS)

### Actionable Signal Dropped by Filter

> For a full catalogue of signal quality issues and exactly where to apply systemic fixes, see [`/docs/check_signals.md`](/docs/check_signals.md).

If a recent, Italy-relevant signal is missing from `detected_signals_filtered.json`, re-run:

```bash
pnpm pipeline --step filter
```

Current strict-type recovery rules include:
- Creditor/debt-restructuring signals with explicit tagged-fund mention → `debt_financing`
- "New/additional contributions to <fund>" signals → `fundraise_announced`

Signal text normalization repairs merged-token artifacts
(e.g. `€62Mof`, `€3.3Mper`, `agreementfor`, `partnershipwith`,
`diMarulloper`, `TechNovaper`) during `filter`, with entity-aware company token
deconcatenation. Repairs propagate to `enrich` outputs on the next run.

### Duplicate NEWS Signal Variants in Raw Store

If `data/derived/detected_signals.json` shows near-duplicate NEWS rows for the same
article (for example old malformed text and a later corrected variant), run:

```bash
python -m fundradar_worker.monitor --slugs fund-slug --force-extract --skip-backoff
```

`SignalStore` coalesces NEWS duplicates by stable identity
(`fund_slug + source_url + title + published_at`) and keeps the better/newer
variant, so corrected re-extractions replace stale malformed entries.

### Multi-fund tagging in `/signals`

Expected behavior:
- A single signal card can show multiple blue fund links in the header.
- The same signal should appear on each tagged fund page without duplicating cards in `/signals`.

How it works:
- The RSS monitor writes `related_fund_slugs` for each signal when multiple funds are involved.
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

When Italian fields remain but translation is blocked or partial (DNS or connectivity
errors, missing API keys), `enrich_signals_openai.py` logs it. If Telegram is configured
(`FUNDRADAR_TELEGRAM_BOT_TOKEN` and `FUNDRADAR_TELEGRAM_CHAT_ID`), it also sends an alert.

Toggles:
- `SIGNAL_TRANSLATION_ALERTS=1` (default on; set `0` to disable the alert)
- `SIGNAL_ENRICH_STRICT_NETWORK=1` (default on):
  - when DNS/API connectivity degrades during enrich, script exits with code `2`
  - pipeline auto-retries and records a step warning instead of silently passing

Latest network health status is persisted to:
- `data/derived/signal_enrichment_network_status.json`

### Rate Limiting / Timeouts

Both fixes below edit `data/derived/domain_policies.json`.

**Fix:** Increase delay in `data/derived/domain_policies.json`:
```json
{ "policies": { "domain.com": { "rate_limit_delay": 5.0 } } }
```

### SSL Certificate Errors

**Fix:** Disable SSL verification in `data/derived/domain_policies.json`:
```json
{ "policies": { "domain.com": { "ssl_verify": false } } }
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
