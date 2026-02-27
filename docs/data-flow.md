# Fundradar Data Flow

All data is stored in JSON files. There is no database.

## Pipeline

```
Website Scrape → Extraction → Portfolio Validation → Entity Resolution → Diff Detection → Signal Generation → JSON Write
```

### Pipeline Steps

```
pnpm pipeline
├── 1. monitor            (fetch pages → extract data → detect changes → write signals + portfolio)
├── 2. rss                (fetch Italian news feeds → match to funds → append signals)
├── 3. translate          (DeepL→Azure→OpenAI — MUST run before filter; filter uses English patterns)
├── 4. normalize_sectors  (canonical 30-sector taxonomy for funds + companies)
├── 5. normalize_portfolio(dedup company names across fund portfolios)
├── 6. enrich_portfolio   (optional — Gemini fills missing sector/HQ/description)
├── 7. filter             (multi-gate quality scoring → write detected_signals_filtered.json)
├── 8. enrich             (AI summaries via OpenAI → write detected_signals_enriched.json)
└── 9. signal_to_portfolio(convert deal/exit signals to portfolio entries — zero API calls)
```

> **Critical ordering**: step 3 (`translate`) MUST precede step 7 (`filter`). The filter's keyword patterns are English-only — Italian signals reaching the filter score lower and get misclassified. See `apps/worker/CLAUDE.md` for full translation architecture.

## Data Sources (by trust tier)

```
TIER 1 — AUTHORITATIVE
Fund Websites  →  monitor.py + extractors  →  portfolio_items.json
                  differ.py                    detected_signals.json

TIER 2 — RELIABLE (expensive)
LinkedIn       →  linkedin/*.py            →  fund_people_stats.json

TIER 3 — RELIABLE (lagging)
AIFI Website   →  aifi_scraper.py          →  db.json + aifi_members_enriched.json

TIER 4 — INDICATIVE (historical, OCR)
PEM PDFs       →  ingest_pem.py            →  pem_deals.json

TIER 5 — SEED DATA
Manual entry                               →  db.json (flagged via data_source)
```

## File → Loader → Page Mapping

| Data File | Loader Function | UI Page |
|-----------|-----------------|---------|
| `data/db.json` | `getAllFunds()` | `/` (home page) |
| `data/db.json` | `getFundBySlug()` | `/funds/[slug]` (header) |
| `data/derived/pem_deals.json` | `getDealsForFund()` | `/funds/[slug]` (deals) |
| `data/derived/portfolio_items.json` | `getPortfolioForFund()` | `/funds/[slug]` (portfolio) |
| `data/derived/fund_people_stats.json` | `getTeamAnalyticsForFund()` | `/funds/[slug]` (team) |
| `data/derived/detected_signals_filtered.json` | `getSignalsForFund()` | `/funds/[slug]` (signals) |
| `data/derived/detected_signals_enriched.json` | `loadUnifiedSignals()` | `/signals` (feed) |

## Signal Processing

Both `/signals` and `/funds/[slug]` pages apply identical signal processing via `signalProcessing.ts`:
- `isGarbageSignal()` — filters nav text, stock photo descriptions, misattributed signals
- `cleanSignalTitle()` — strips "Press release" prefix, date artifacts
- `cleanSignalText()` — strips read-time labels, fixes spacing, strips leading labels
- `reclassifySignalType()` — corrects misclassified signal types (e.g. fundraise → deal)

### Multi-fund signal tags

- RSS/news signals can involve more than one fund. Worker output now stores this in
  `related_fund_slugs` while still emitting one row per primary `fund_slug`.
- `loadUnifiedSignals()` merges duplicate cross-fund copies into one feed card and keeps all
  associated `related_fund_slugs` for UI rendering.
- `getSignalsForFund()` includes signals where the requested slug appears in
  `related_fund_slugs` (not only where it is the primary `fund_slug`).
- Active-party guardrails:
  - worker (`rss_monitor.py`) drops speculative-only candidate slugs when active slugs are present
  - web (`signalFundTags.ts`) suppresses inferred speculative mentions in sentence-local context

## Portfolio Validation

Portfolio entries are validated in two layers:
1. **Worker** (`portfolio_validation.py`): Runs before writing to `portfolio_items.json` — rejects garbage at extraction time
2. **Web app** (`data.ts`): Runs at display time as defense-in-depth for manual entries and new garbage patterns
| `data/derived/fund_aliases.json` | `slug_normalizer.py` | canonicalize/deny slugs during ingestion |

## Data Source Hierarchy

When two sources disagree, the higher-tier source wins.

| Tier | Source | Trust Level | What it provides |
|------|--------|-------------|------------------|
| 1 | **Fund Website** | Authoritative | Portfolio (current state), fund news, team pages |
| 2 | **LinkedIn** | Reliable | Team composition, hiring signals, tenure data |
| 3 | **AIFI** | Reliable | AUM, fund count, investment ranges, SFDR data |
| 4 | **PEM Reports** | Reliable (deal existence) | Historical deals. Status must be verified. |
| 5 | **News** | Unverified | Third-party articles. May contain rumors. |
| 6 | **Manual** | Indicative | Seed data with required source links. |

### Conflict Resolution

- **Portfolio status**: Fund website wins. PEM confirms deal existence but status must be verified against newer evidence.
- **Fund metadata** (AUM, team size): AIFI > Manual.
- **Team data**: LinkedIn > Fund website (more granular).
- **PEM OCR caveat**: Reliable for deal existence, not for current status.

## Entity Resolution

For each extracted company:
1. Normalize name (lowercase, remove legal suffixes)
2. Check existing aliases
3. Check by normalized name
4. Fuzzy match (90% Jaccard threshold)
5. Create new entity if truly new

## Caching

All web app loaders use module-level caching (simple variable). Cache persists for the duration of the server process. No TTL — restart `pnpm dev` to refresh data after worker runs.

## Reliability Contract

Every change must be:
- **Source-cited**: link to original page
- **Timestamped**: `observed_at` recorded
- **Confidence-scored**: extraction confidence attached

## Worker-Internal Files (not consumed by web)

- `snapshots.json` — content snapshots for change detection
- `circuit_state.json` — circuit breaker state
- `url_status.json` — URL health tracking
- `monitor_checkpoint.json` — pipeline resume state
- `blobs/{hash}.html` — cached page content
