# Fundradar - Claude Code Instructions

## What is this project?
A free, public directory of Italian PE/VC funds with monitored "signals" (news, hires, deals). The value is clean, searchable data with source citations. All data is freely accessible — no account required. Users can subscribe to weekly email signal digests via Stripe.

**Live**: [fundradar.vercel.app](https://fundradar.vercel.app) | **Repo**: [github.com/filippoteodoro/fundradar](https://github.com/filippoteodoro/fundradar)

## CRITICAL: Entity Scope — PE/VC ONLY

**The tracked fund universe in `db.json` is the ONLY source of truth.** PEM deals reference many historical fund names — IGNORE those counts (defunct, renamed, not tracked).

**Gemini-confirmed zero-Italy funds are hidden from the website.** If Gemini audits a fund and confirms it has zero Italian assets (`completion_ready=True`, `italian_portfolio_count=0`, `missing_assets=[]`), the fund must be removed from the public website. Add its slug to `data/derived/gemini_fund_asset_zero_italy_verified.json` → `verified_slugs[]`. Implementation: filter these out in `getAllFunds()` in `data.ts`. See `apps/web/CLAUDE.md` for the full implementation spec.

Only Private Equity, Venture Capital, and Growth Equity funds belong in db.json. **NEVER add:**
- **Asset managers** (Generali Investments, Amundi, BlackRock) — diversified portfolios, not PE/VC
- **Banks** (Banca Generali, BancoBPM Invest) — deposit-taking institutions
- **Regional agencies** (Trentino Sviluppo, Lazio Innova, Finlombarda) — public agencies
- **Credit vehicles** (Clessidra Capital Credit SGR) — private debt, not equity

Blocked via `invalid_slugs` in `fund_aliases.json` and `EXCLUDED_SLUGS` in `merge-aifi-metrics.ts`. When in doubt: check the entity's website — "asset management" / "wealth management" / "banking" / "credit" = not PE/VC.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web | Next.js 14 (App Router), TypeScript, React 18, Recharts |
| Data | File-based JSON (`data/` and `data/derived/`) — NO database |
| Worker | Python 3.10+, Playwright, pydantic |
| Types | `@fundradar/shared` (TypeScript, consumed by web) |
| Monorepo | pnpm workspaces |
| Testing | Vitest (web), pytest (worker) |
| Hosting | Vercel (auto-deploys from `main`, Root Directory: `apps/web`) |

**NO database, NO Supabase, NO Tailwind (inline styles), NO Turbo, NO user accounts.**

## Project Structure

Folder-level only — individual extractors and scripts are not listed (they change frequently).

```
apps/
  web/                          Next.js frontend (see apps/web/CLAUDE.md)
    src/
      app/                        Next.js App Router routes (pages, API routes)
      components/                 React components
      lib/                        ALL data loading + signal processing (data.ts, signals_unified.ts, signalProcessing.ts)
  worker/                       Python pipeline (see apps/worker/CLAUDE.md)
    fundradar_worker/             Core importable package
      strategies/
        extractors/               Fund-specific extractors — one .py per fund (DO NOT list individually)
      linkedin/                   LinkedIn scraping modules (Apify, HarvestAPI)
    scripts/                      Standalone pipeline scripts (filter, enrich, translate, signal_to_portfolio, …)
    tests/                        pytest test suite

data/
  derived/                      Worker output JSON — committed to git, consumed by web
  AIFI/                         AIFI member source data (all.csv is authoritative for fund URLs)
  models/                       ML classifier joblib files
  pem/                          PEM PDF source files — NEVER Read() these

packages/
  shared/src/                   Shared TypeScript types (types.ts: Fund, Signal, Deal, …)

scripts/                        Gemini audit + data maintenance Python scripts (one-off / manual runs)
  audit-fund-assets-gemini.py   Canonical Gemini fund audit runner
  run-audit-fund-assets-gemini-parallel.py  Parallel shard runner
  enrich-fund-metadata-gemini.py
  generate-fund-descriptions-gemini.py
  enrich-top-fund-portfolios-gemini.py
  verify-portfolio-gemini.py
  import-manual-gemini-fund-responses.py
  reconcile-gemini-fund-asset-audit.py
  recover-gemini-fund-asset-audit-from-logs.py
  (+ audit/validation helpers)
```

## Commands

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start web dev server |
| `pnpm build` | Build shared types then web app |
| `pnpm lint` / `pnpm typecheck` / `pnpm test` | Lint, type-check, test |
| `pnpm seed` | Run seed scripts (has safety guard — use `--force` to override) |
| `pnpm worker:monitor` | Fetch websites, extract data, detect changes |
| `pnpm worker:ingest` | Process PEM PDFs → `pem_deals.json` |
| `pnpm worker:aifi` | Scrape AIFI member data |
| `pnpm worker:geocode` | Geocode addresses → `fund_coordinates.json` |
| `pnpm merge-aifi` | Merge AIFI data into `db.json` |
| `pnpm aifi:full` | AIFI scrape + merge |
| `pnpm pipeline` | Full: monitor → rss → translate → normalize_sectors → normalize_portfolio → enrich_portfolio → filter → enrich → signal_to_portfolio |
| `pnpm pipeline --force-extract` | Re-extract even if content unchanged |
| `pnpm pipeline --slugs s1,s2` | Run for specific fund slugs |
| `pnpm pipeline:signals` | Filter + enrich only (skip fetching) |
| `pnpm pipeline:signals-to-portfolio` | Convert deal/exit signals to portfolio entries (standalone) |
| `pnpm audit:quality` | Fund data quality audit |

## Critical Rules

### 1. Caching — THE #1 BUG SOURCE
`data.ts` has module-level caches with **NO TTL, NO invalidation**. Worker writes JSON → **restart `pnpm dev` to see changes**. See `apps/web/CLAUDE.md` for full cache list.

### 2. Type Contract — NOT ENFORCED AT RUNTIME
Python writes dicts to JSON with no schema validation. TypeScript types are compile-time only. Known drift exists between Python output and TS declarations. **When changing a type**: update `types.ts`, update Python dicts, update `data.ts` loaders, and verify JSON output matches.

### 3. Signal Dual-Loading
- `/signals` → `signals_unified.ts` → enriched → filtered → raw
- `/funds/[slug]` → `data.ts` → filtered ONLY
- Both share processing via `signalProcessing.ts`
- Dedup logic in 2 places: Python `filter_signals.py` and `signals_unified.ts` — update both
- Classification must match in **3 places**: Python `signal_patterns.py` + `signal_corrections.py` (shared by filter + enricher) AND TypeScript `signalProcessing.ts`
- Text cleaning is shared via `signal_text_utils.py` — `clean_display_text()` is the single entry point for all signal text fields (title, what_changed, enriched_summary, diff_summary). Both filter and enricher import from it.

### 4. Data Reliability Contract
Every signal MUST have: `source_url`, `source_name`, `published_at` (if known), `observed_at`. All enrichment must have a verifiable `{field}_source_url`. AI is a data collection aid, not a data source — never store "ai_inferred" as a source.

### 5. Model Policy
- **OpenAI**: Model is centralised in `OPENAI_MODEL` in `apps/worker/fundradar_worker/paths.py` — always import from there, never hardcode. Current value: `gpt-5-mini`. NEVER use ChatGPT 4o (hallucinates too much).
- **Gemini**: Model is centralised in `GEMINI_MODEL` in `apps/worker/fundradar_worker/paths.py` — always import from there, never hardcode. Current value: `gemini-3-flash-preview`. NEVER use `gemini-2.x` (hallucinates more). NEVER use Flash-Lite variants for data enrichment — Flash-Lite is optimised for throughput, not accuracy; fact-extraction quality is meaningfully lower.

### 6. File-Based Architecture
- All data in JSON files — worker writes to `data/derived/` via `safe_json_write()` (atomic)
- Web reads via `data.ts` — NEVER bypass it to read JSON directly in components
- Path resolution via `getRepoRoot()` — NEVER hardcode absolute paths
- NEVER `Read()` PEM PDFs — use `pnpm worker:ingest`

### 7. Scope
Italy-only funds. Solo project — keep solutions minimal. Avoid over-engineering.

### 8. Documentation Process — Update Docs Immediately
**Whenever you discover anything new about the codebase** — a subtle behavior, a non-obvious pattern, a bug root cause, a pitfall — **update the relevant CLAUDE.md before the session ends**. Do not defer to a separate "docs pass".

- Root `CLAUDE.md` — cross-cutting rules, architecture patterns, pitfalls
- `apps/web/CLAUDE.md` — web-specific behaviors, dedup details, component logic
- `apps/worker/CLAUDE.md` — pipeline, patterns, signal classification details

If you learned it during a session, write it down. This is what prevents the same bug from being debugged twice.

## Data Pipeline

### Source → Output → Loader

| Data | Output File | Web Loader |
|------|-------------|------------|
| Fund list | `db.json` | `getAllFunds()` |
| Deals | `pem_deals.json` | `getDealsForFund()` |
| Portfolios | `portfolio_items.json` | `getPortfolioForFund()` |
| Signals (filtered) | `detected_signals_filtered.json` | `getSignalsForFund()` |
| Signals (enriched) | `detected_signals_enriched.json` | `loadUnifiedSignals()` |
| Team stats | `fund_people_stats.json` | `getTeamAnalyticsForFund()` |
| LinkedIn URLs | `linkedin/fund_linkedin_urls.json` | merged at load time |
| Fund coordinates | `fund_coordinates.json` | merged into `db.json` via `merge-aifi` |
| Unknown fund gaps | `unknown_fund_gaps.json` | worker dedup state only (not consumed by web) |

**9-step pipeline** (see `apps/worker/CLAUDE.md` for each step's full spec):
`monitor → rss → translate (DeepL→Azure→OpenAI) → normalize_sectors → normalize_portfolio → enrich_portfolio (Gemini) → filter (quality scoring) → enrich (AI summaries) → signal_to_portfolio (local)`

**Translation order is CRITICAL**: `translate` runs at step 3, BEFORE `filter`. The filter uses English keyword patterns — Italian signals reaching it untranslated score lower and get misclassified. See `apps/worker/CLAUDE.md` for the full translation architecture and why removing DeepL cost $15.

Content hashing skips unchanged pages — use `--force-extract` after updating extractors. **Pipeline auto-resumes if interrupted** — each step's progress is tracked in `data/derived/*_progress.json` files; re-running picks up where it left off.

**When signals have quality issues** (wrong type, missing, bad text, wrong fund, not in portfolio): see `docs/check_signals.md` — it has the full catalogue of issue types and exactly which function to edit for each.

### Address Data
`db.json` is the **only** source of address/coordinate data for the web app. `fund_coordinates.json` is a geocoding cache consumed only by `merge-aifi-metrics.ts`. To update: `pnpm worker:geocode && pnpm merge-aifi`. See `apps/web/CLAUDE.md` for map resolution chain.

## Architecture Patterns
- **Extraction**: fund-specific extractors take priority; generic strategies only run when no custom extractor returns results
- **Extractor URLS**: each extractor's `URLS` dict is the single source of truth for which URLs to fetch
- **Entity resolution**: normalizes company names, fuzzy matching at 90% Jaccard
- **Atomic writes**: `safe_json_write()` — NEVER use bare `open()/json.dump()`
- **Signal quality**: defense-in-depth — Python `filter_signals.py` is primary gate, TS `signalProcessing.ts` is safety net
- **Signal shared modules**: `signal_patterns.py` (regex patterns), `signal_corrections.py` (type corrections + `detect_all_signal_types()`), `signal_text_utils.py` (text cleaning via `clean_display_text()`) — all consumed by filter and enricher
- **Multi-type signals**: `signal_types?: SignalType[]` on `Signal` holds all types present in a signal (e.g. `["fundraise_closed", "exit_announced"]`); primary type first. Written by both filter and enricher via `detect_all_signal_types()`. Rendered as secondary badges in `SignalCard.tsx`.
- **Unknown fund alerting**: `fund_gap_detector.py` detects Italian-style fund names in signal text not in db.json; `alerting.py::send_unknown_fund_alerts()` sends Telegram alerts; dedup state in `data/derived/unknown_fund_gaps.json`
- **Extractor vs pipeline boundary**: extractors handle site-specific HTML parsing/URL routing; pipeline handles universal classification language (e.g. "takes a stake" → deal). Fund-specific metadata (e.g. ecosystem newsrooms) goes in `db.json`, not hardcoded in pipeline code
- **Fund metadata flags in db.json**: `is_ecosystem_newsroom` (newsroom covers the whole market, not just the fund's own activity — currently: cdp-venture-capital, itago, faro-value). Enforced in `_is_misattributed_signal()` in `filter_signals.py` — applies to ALL sources (RSS, web). To add a new ecosystem newsroom: set `"is_ecosystem_newsroom": true` in db.json, no code change needed.

## Key Files

| File | Role |
|------|------|
| `apps/web/src/lib/data.ts` | ALL data loading, multiple module-level caches |
| `apps/web/src/lib/signals_unified.ts` | Signal loading for `/signals` page |
| `apps/web/src/lib/signalProcessing.ts` | Shared signal processing (both paths) |
| `packages/shared/src/types.ts` | Type definitions (Fund, Signal, Deal, DataSource) |
| `apps/worker/fundradar_worker/pipeline.py` | Pipeline orchestration |
| `apps/worker/fundradar_worker/monitor.py` | Main fetch/extract/diff engine + exit detection |
| `apps/worker/fundradar_worker/translator.py` | Shared translation module (DeepL→Azure→OpenAI) |
| `apps/worker/scripts/filter_signals.py` | Primary quality gate (scoring, geo, dedup, reclassification) |
| `apps/worker/scripts/signal_patterns.py` | Single source of truth for shared regex patterns |
| `apps/worker/scripts/signal_corrections.py` | Shared post-classification corrections + `detect_all_signal_types()` (filter + enricher) |
| `apps/worker/scripts/signal_text_utils.py` | Shared text cleaning: `clean_display_text()`, `fix_spacing()`, `normalize_monetary_values()` |
| `apps/worker/scripts/signal_to_portfolio.py` | Signal→portfolio conversion (local) |
| `apps/worker/scripts/fund_gap_detector.py` | Detects unknown fund names in signal text; alerts via Telegram |
| `apps/worker/fundradar_worker/strategies/extractors/` | Fund-specific extractors |

## Deployment (Vercel)

**Live**: [fundradar.vercel.app](https://fundradar.vercel.app)

- **Repo**: `filippoteodoro/fundradar` on GitHub
- **Vercel Root Directory**: `apps/web` (set in Vercel dashboard)
- **Config**: `apps/web/vercel.json` — install and build commands navigate up to repo root
- **Static generation**: All fund pages pre-rendered at build time via `generateStaticParams()`
- **Dynamic OG image**: `opengraph-image.tsx` generates a 1200x630 PNG at the edge
- **Readonly mode**: `IS_READONLY` guard in `auth.ts`, `watchlist.ts`, `subscribers.ts` prevents filesystem writes
- **Auth API routes**: Return 503 on Vercel (no user accounts)
- **Login/signup/watchlists**: Redirect to `/subscribe`
- **Data files**: Committed to git in `data/derived/` — web-essential JSONs only (~9MB)
- **`outputFileTracingIncludes`**: In `next.config.js`, ensures Vercel serverless bundler includes `data/**/*.json`
- **Base URL**: `src/lib/baseUrl.ts` uses `NEXT_PUBLIC_BASE_URL` > `VERCEL_URL` > `fundradar.org`

### Deployment workflow
1. Run `pnpm pipeline` locally to update data
2. Commit updated data files in `data/derived/`
3. Push to `main` — Vercel auto-deploys

### No user accounts
There are no login, signup, or watchlist features on production. All data is freely accessible. Users subscribe to email signal digests via `/subscribe` (Stripe payments). The auth/watchlist code exists but is disabled on Vercel.

### Subscriptions & Digest Workflow

**Current state (manual):**
1. Users subscribe via `/subscribe` → Stripe Checkout (supports Apple Pay / Google Pay)
2. Stripe is the sole source of truth for subscribers — no local `subscribers.json` on Vercel
3. To build a digest: `pnpm -F scripts digest:build --dry-run` (pulls active subscribers from Stripe API via `STRIPE_SECRET_KEY`)
4. Review `data/derived/digest/latest_digest.txt` and `latest_recipients.csv`
5. Send manually (no automated sending yet)

**Future state:**
- Resend integration for automated email delivery (requires custom domain for sender address)
- Vercel Cron Job or GitHub Action to trigger weekly digest build + send
- Unsubscribe link in digest emails pointing to Stripe customer portal

**Key files:**
- `scripts/build-weekly-digest.ts` — builds digest content, pulls recipients from Stripe
- `apps/web/src/app/api/stripe/checkout/route.ts` — creates Stripe Checkout sessions
- `apps/web/src/app/api/stripe/webhook/route.ts` — handles subscription lifecycle events
- `apps/web/src/lib/subscribers.ts` — local subscriber store (unused on Vercel, kept for local dev)

## Common Pitfalls

Items covered in detail by sub-project CLAUDE.md files are marked with → reference. Unique root-level pitfalls:

1. **Worker runs but UI shows old data** → restart `pnpm dev` (→ `apps/web/CLAUDE.md`)
2. **Adding subpage URLs to `monitor-urls.md`** → NEVER. This file has base domain URLs only. Subpage routing is in extractors' `URLS` dicts.
3. **Assuming fund website domains without checking AIFI** → verify URLs against `data/AIFI/all.csv`. AIFI is authoritative for member website URLs.
4. **AIFI scraper sets wrong HQ for global funds** → Italian branch gets written as HQ. After ANY AIFI merge, cross-check `offices[]` is_hq entries against top-level `hq_*` fields. Preserve Italian office in `offices[]` when fixing global HQ.
5. **Mentioning LinkedIn on the website** → NEVER mention "LinkedIn" in user-facing text. Use "public profiles" instead. Icon links are fine.
6. **Deleting global portfolio entries** → DON'T. Frontend filters by Italy via `isItalianCompany()`. Global data provides context.
7. **LinkedIn scraping is ON-DEMAND ONLY** → Uses paid Apify. NEVER add to `pnpm pipeline`. Audit `fund_linkedin_urls.json` against `db.json` periodically.
8. **Career signals are valuable** → Do NOT add career keywords to noise filters. `job_posting` type is supported end-to-end.
9. **Using wrong fund slugs** → ALWAYS look up from `db.json`, never guess. See slug reference below.
10. **After AIFI scrape** → verify names are brand names (not legal entity names). No `(Italia)`, no `Associati` suffix. `name` must match fund's own website.
11. **AI is never disclosed in UI** — never say a field is "AI-generated." Reference sources, not AI.
12. **No "as of" labels** — claim data is current. If stale, update the data instead.
13. **Never delete enrichment progress/output files** → `signal_enrichment_progress.json` and `detected_signals_enriched.json` prevent costly re-translation and re-enrichment. Deleting either forces full re-run (~$2–5 in OpenAI credits). See `apps/worker/CLAUDE.md` for full cost control rules. **Note**: `enriched_summary` coverage <100% is intentional — title-redundant summaries are deliberately cleared (the frontend shows the title instead). This is NOT data loss.
14. **Fix signals by editing JSON directly, not re-running enricher** → Direct edits to `detected_signals_enriched.json` are free. Re-running `pnpm pipeline:signals` costs ~$0.30–0.50/run. During debugging, 50 re-runs = $15+. **But JSON edits are one-off patches — new signals will have the same problem.** For any recurring issue, apply a systemic code fix. See `/docs/check_signals.md` for the full catalogue of issue types and exactly where to fix each one in the pipeline.
15. **NEVER remove or bypass the DeepL translation layer** → DeepL is the primary translation provider (500K chars/month free × 2 keys). Removing it forces all translation through OpenAI at ~$0.10/run just for translation. The `translate` pipeline step (step 3) runs before `filter` — this order is intentional: filter patterns are English-language, translating first improves signal classification quality. See `apps/worker/CLAUDE.md` for the full translation architecture.
16. **NEVER move translation after the filter step** → The filter (`filter_signals.py`) uses English-language keyword patterns (deal, exit, fundraise, etc.). Italian signals hitting the filter score lower and get misclassified. Translation must run at step 3 (before step 7/filter). The enricher's translation pass is a safety net only, not the primary path.
17. **DeepL quota exhaustion sends Telegram alerts automatically** → Both keys exhausted = Telegram alert fires. Monthly quota resets on the 1st. `data/derived/deepl_quota_state.json` tracks per-key exhaustion — delete this file to reset state if needed.
18. **NEVER block on long-running Gemini/pipeline scripts** → Pipeline runs, Gemini audit/enrichment scripts, and OpenAI enrichment can take **minutes to hours**. ALWAYS run them with `run_in_background: true`. Monitor progress via `tail -N outputfile` and `ps aux | grep scriptname`. Check progress JSON files (`gemini_fund_asset_audit_progress.json`, `fund_metadata_enrichment_progress.json`, `signal_enrichment_progress.json`) instead of blocking waits. NEVER run two instances of the same Gemini script — they share progress files and will corrupt each other.
19. **NEVER appear stuck or idle** → When launching multiple parallel agents (research, enrichment, etc.), ALWAYS continue doing productive work while waiting. If you have 5 research agents running, start processing results from the first one that returns immediately — do NOT wait for all of them. If a background task takes > 2 minutes, check progress once and move on to other work. The user should ALWAYS see you actively producing output. **Batch work pattern**: launch agents → process results as they arrive → launch next batch. NEVER launch many agents and then sit idle waiting for all results.
20. **New sector tag in portfolio data breaks CI** → `sectorGroups.test.ts` scans all current `portfolio_items.json` entries and fails if any sector tag is unmapped. Whenever a new sector label appears in scraped/manual portfolio data, add it to `SECTOR_TAG_ALIASES` in `apps/web/src/lib/sectorGroups.ts` (map it to the nearest canonical sector or a strategy bucket like `Financial Services`). Run `pnpm test` locally before pushing.
21. **Semantic dedup false-positives in signals_unified.ts** → `DEDUP_STRUCTURAL_WORDS` strips fund-name slug words AND English stop-words before computing word overlap. If the stop-words are removed, ecosystem newsroom funds (CDP Venture Capital, Itago) whose signal titles all begin with the fund name will have many coincidental function-word matches and get falsely deduped. **NEVER remove the English stop-words from `DEDUP_STRUCTURAL_WORDS`** — they prevent ~7+ CDP signals from being incorrectly collapsed per run. See `apps/web/CLAUDE.md` for full dedup architecture details.
22. **`rebuild-gemini-audit-from-canonical.py` WIPES API run data** → This script completely replaces `gemini_fund_asset_audit.json` from the canonical JSONL. API runs (via `audit-fund-assets-gemini.py`) write directly to the output JSON — they are **NOT** recorded in the JSONL. Running rebuild after an API audit will erase all API results that were not manually exported from AI Studio. **Only run rebuild when the output file is lost or corrupted.** Correct flow when supplementing an API audit with one manual import: (1) `import-manual-gemini-fund-responses.py` → (2) re-run `audit-fund-assets-gemini.py --slugs <slug>` to merge. Never run rebuild as the merge step.
23. **`deal_amount` is often absent but extractable** → `filter_signals.py` has a `_RE_EXTRACT_AMOUNT` backfill that reads amount from title/what_changed. When a deal signal has no structured amount field, the filter fills it automatically. Don't add amount extraction to other pipeline steps — it runs once at filter time.
24. **Cross-fund URL dedup is in the filter** → `_cross_fund_url_dedup()` in `filter_signals.py` runs after semantic dedup and keeps only the highest-quality copy of any signal that was matched to multiple funds from the same source URL. The runner-up signals are dropped; the winner gets a `co_fund_slugs` list. This is intentional — having 3 copies of the same article is worse than having 1 with context.
25. **`portfolio_update` vs `deal_announced` for capex** → When a fund's portfolio company invests in a plant/facility/production site (capex), this is `portfolio_update` — NOT `deal_announced`. Signal pattern: `[Company] (FundName) invests €Xm for new [plant/facility/hub/...]`. The parenthetical fund name signals existing ownership. Wired in `correct_deal()` in `signal_corrections.py`.
26. **CI new-fund gate fires on routine pipeline runs** → `scripts/check_new_fund_gate.py` triggers whenever `db.json` or extractor files change. If all changed funds already existed in db.json (pipeline just updated fields), they are treated as **established** and skip strict data-completeness checks (portfolio enrichment 100%, signal parity, signal completeness, Italy asset verification). Only genuinely new db.json entries (no prior slug) face full checks. The gate requires both `gemini_fund_asset_audit.json` AND `new_fund_completion_report.json` to be in the commit diff — touch the audit file's `last_gate_verification` field to satisfy the freshness check after a pipeline run.
27. **Italian signal titles slipping through filter** → If `title_original` is absent (translation was skipped), the filter applies a `-30` quality penalty when 2+ Italian-specific content words appear in a short title (≤15 words). To fix existing signals: edit titles directly in `detected_signals_filtered.json` and `detected_signals_enriched.json` (free), set `title_original` to the Italian original. Do NOT re-run the enricher (costs $0.30+/run).
28. **Ecosystem newsroom signals from RSS aggregators** → Signals from BeBeez/Il Sole 24 Ore attributed to ecosystem newsroom funds (CDP VC, Itago, Faro Value) must contain the fund's distinctive slug keyword in title/what_changed. The ecosystem check now applies to ALL sources, not just fund-website-domain signals. Defense-in-depth: negative geo downgrade flips `italy_relevant=True→False` when text has non-Italian EU geography (Bavaria, Munich, etc.) without Italy mention AND no relevance evidence. `signal_to_portfolio.py` also skips `italy_relevant=False` signals.

For portfolio-specific pitfalls (PEM merge, garbage entries, manual entries, status detection): see `apps/web/CLAUDE.md`.
For extractor/worker pitfalls (force-extract, PortfolioStore guard, site configs): see `apps/worker/CLAUDE.md`.

## Known Technical Debt

Intentional tradeoffs — don't "fix" without explicit request:

- **data.ts is a large single file** — explicit and grep-friendly
- **Portfolio merge mutates in-place** — safe because cache repopulates on restart
- **No runtime type validation** — JSON files are trusted
- **Dedup logic in 2 places** — Python filter and signals_unified.ts independently
- **Team analytics is dummy data** — waiting for real LinkedIn data; team scoring disabled in `fundQuality.ts`
- **PEM deal status needs verification** — reliable for deal existence, not current status
- **Signal importance is computed at runtime** — `SignalsFeed.tsx:getImportanceScore()` computes from quality_score + evidence_score + type bonus + fund priority + Italy bonus. NOT stored in JSON. Also computed in `build-weekly-digest.ts`. Don't add an `importance` field to the pipeline output — it's by design.
- **enriched_summary is intentionally <100%** — title-redundant summaries are cleared (85% word overlap check). Frontend falls back to title. NOT data loss.

## Fund Slug Reference — Top 25 by AUM

**CRITICAL: ALWAYS look up slugs from `db.json` — NEVER guess.** Old slugs resolve via `fund_aliases.json`.

| Fund Name | Slug | Tricky? |
|-----------|------|---------|
| Blackstone | `blackstone` | |
| Apollo | `apollo` | |
| KKR | `kkr` | |
| Macquarie | `macquarie` | |
| Ares Management | `ares-management` | NOT `ares` |
| Carlyle | `carlyle` | |
| EQT | `eqt` | |
| Bain Capital | `bain-capital` | |
| Ardian | `ardian` | |
| Partners Group | `partners-group` | |
| Advent International | `advent-international` | NOT `advent` |
| Permira | `permira` | |
| Apax Partners | `apax-partners` | |
| H.I.G. Capital | `h-i-g-capital` | |
| Clessidra SGR | `clessidra-sgr` | |
| CDP Venture Capital | `cdp-venture-capital` | |

Lookup: `python3 -c "import json; [print(f['slug'], f['name']) for f in json.load(open('data/db.json'))['funds'] if 'SEARCH' in f.get('name','').lower()]"`

## Data Safety & Backup

The repo lives under iCloud Drive, so the effective backup tiers are:

| Tier | What | Where |
|------|------|-------|
| 1 | Local working copy | `~/Library/Mobile Documents/…/Fundradar/` |
| 2 | Cloud sync | iCloud (Apple servers, near-real-time) |
| 3 | Git remote | GitHub (`filippoteodoro/fundradar`) — offsite, versioned |

**Committed files** (all three tiers): source code, `data/db.json`, `data/derived/portfolio_items.json`, `data/derived/detected_signals_*.json`, `data/derived/pem_deals.json`, `data/derived/fund_people_stats.json`, `data/derived/gemini_fund_asset_zero_italy_verified.json`.

**Gitignored files** (iCloud only — tiers 1+2, NOT on GitHub):

| File / Pattern | Why gitignored | Risk if lost |
|----------------|---------------|-------------|
| `data/derived/linkedin/raw/` | Sensitive scraped data, Apify cost to regenerate | **HIGH — known 3-2-1 gap, no GitHub copy** |
| `data/derived/gemini_fund_asset_audit*.json` | Large/noisy intermediate audit output | Medium — months of audit work, but derived output (`zero_italy_verified.json`) is committed |
| `data/models/` | ML classifier joblib files | Low — can be retrained |
| `data/pem/*.pdf` | Large PDFs | Low — physical source docs |

**`signal_enrichment_progress.json` is committed** (exception to the `*_progress*` glob) — losing it forces full re-enrichment of all signals at ~$2–5 API cost.

**Known gap — `linkedin/raw/`**: This is the one file set with no GitHub copy. iCloud is the only offsite backup. Do not delete these files without an explicit off-iCloud backup. `git clean -fdx` will wipe them permanently.

**IMPORTANT — "NEVER DELETE" warnings in these docs apply to gitignored files.** They are NOT recoverable from GitHub. iCloud Versions (right-click → Revert To) is the only safety net. A `git clean -fdx` will wipe them permanently.

**`gemini_fund_asset_zero_italy_verified.json` is committed** — it controls which funds are hidden from the website and must survive a fresh clone.

## Where to Start

1. Read `apps/web/CLAUDE.md` for web-specific instructions (caching, portfolio merge, signal loading)
2. Read `apps/worker/CLAUDE.md` for worker-specific instructions (extractors, pipeline, status detection)
3. Read `/docs/spec.md` for features and sprint status
4. Read `/docs/check_signals.md` to diagnose and fix signal quality issues (text, classification, filtering, portfolio)
5. Run `pnpm dev` to verify setup works
