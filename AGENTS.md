# Fundradar — Agent and Contributor Rules

This file holds the project-wide rules for contributors and their coding agents. `CLAUDE.md` imports it.

## What is this project?
A free, public directory of Italian PE/VC funds with monitored "signals" (news, hires, deals). The value is clean, searchable data with source citations. All data is free to read. There are no accounts and no payments. The project is MIT open source and has no active maintainer.

**Live**: [fundradar.vercel.app](https://fundradar.vercel.app) | **Repo**: [github.com/filippoteodoro/fundradar](https://github.com/filippoteodoro/fundradar)

## CRITICAL: Entity Scope — PE/VC ONLY

**The tracked fund universe in `db.json` is the ONLY source of truth.** PEM deals reference many historical fund names. Ignore those counts (defunct, renamed, not tracked).

Only Private Equity, Venture Capital, and Growth Equity funds belong in `db.json`. **NEVER add:**
- **Asset managers** (Generali Investments, Amundi, BlackRock) — diversified portfolios, not PE/VC
- **Banks** (Banca Generali, BancoBPM Invest) — deposit-taking institutions
- **Regional agencies** (Trentino Sviluppo, Lazio Innova, Finlombarda) — public agencies
- **Credit vehicles** (Clessidra Capital Credit SGR) — private debt, not equity

**To block a non-PE/VC entity** from tracking and from gap-detector alerts, add it to `db.json["excluded_entities"]` (top-level array, next to `"funds"`). Each entry: `{"slug": "...", "name": "...", "reason": "..."}`. This array is the single source of truth for vetted-but-excluded entities. `slug_normalizer.py` merges it into its `invalid_slugs` set, which feeds slug normalization and the gap detector. Also add the slug to `EXCLUDED_SLUGS` in `scripts/merge-aifi-metrics.ts` to block the AIFI merge. When in doubt, read the entity's website: "asset management", "wealth management", "banking" or "credit" means not PE/VC.

`fund_aliases.json["invalid_slugs"]` is for **garbage slug artifacts only** (junk strings from bad extraction, ambiguous partial names like `partners`, `investimento`). Do NOT add real entity names there.

**Zero-Italy rule.** A fund that the Gemini asset audit confirms has zero Italian assets (`completion_ready=True`, `italian_portfolio_count=0`, `missing_assets=[]`) must not appear on the website. Add its slug to `data/derived/gemini_fund_asset_zero_italy_verified.json` → `verified_slugs[]`. The audit completion checks read this list. The web app does not filter it yet: `getAllFunds()` in `data.ts` still returns these funds. The implementation spec is in `apps/web/CLAUDE.md`.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web | Next.js 14 (App Router), TypeScript, React 18, Recharts |
| Data | File-based JSON (`data/` and `data/derived/`) — NO database |
| Worker | Python 3.10+, Playwright, pydantic |
| Types | `@fundradar/shared` (TypeScript, consumed by web) |
| Monorepo | pnpm workspaces |
| Testing | Vitest (web), pytest (worker) |
| Hosting | Vercel (Root Directory: `apps/web`) |

**NO database, NO Supabase, NO Tailwind (inline styles), NO Turbo, NO user accounts.**

## Project Structure

Folder level only. Individual extractors and scripts are not listed.

Keep the repo root lean. One-off audit scripts, reports, unused assets and completed planning material go under `archive/`.

```
apps/
  web/                          Next.js frontend (see apps/web/CLAUDE.md)
    src/
      app/                        App Router routes (pages, text routes)
      components/                 React components
      lib/                        ALL data loading + signal processing (data.ts, signals_unified.ts, signalProcessing.ts)
  worker/                       Python pipeline (see apps/worker/CLAUDE.md)
    fundradar_worker/             Core importable package
      strategies/
        extractors/               Fund-specific extractors — one .py per fund
      linkedin/                   LinkedIn scraping modules (see docs/linkedin-scraping.md)
    scripts/                      Pipeline step scripts (filter, enrich, translate, signal_to_portfolio, …)
    tests/                        pytest suite

data/
  db.json                       Fund directory (committed, curated)
  derived/                      Worker output JSON — web-consumed files are committed
  AIFI/                         AIFI member source data (all.csv is authoritative for fund URLs)
  models/                       ML classifier joblib files (gitignored)
  pem/                          PEM PDF source files (gitignored) — NEVER Read() these

packages/
  shared/src/                   Shared TypeScript types (types.ts: Fund, Signal, Deal, …)

scripts/                        Gemini audit and data maintenance scripts (see scripts/README.md)
```

## Commands

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start web dev server |
| `pnpm build` | Build shared types then web app |
| `pnpm lint` / `pnpm typecheck` / `pnpm test` | Lint, type-check, test (TypeScript) |
| `cd apps/worker && pytest` | Worker tests |
| `pnpm seed` | Run seed script (has a safety guard — `--force` overrides it) |
| `pnpm worker:monitor` | Fetch websites, extract data, detect changes |
| `pnpm worker:ingest` | Process PEM PDFs → `pem_deals.json` |
| `pnpm worker:aifi` | Scrape AIFI member data |
| `pnpm worker:geocode` | Geocode addresses → `fund_coordinates.json` |
| `pnpm merge-aifi` | Merge AIFI data and coordinates into `db.json` |
| `pnpm aifi:full` | AIFI scrape + merge |
| `pnpm pipeline` | Full pipeline (10 steps, see below) |
| `pnpm pipeline --force-extract` | Re-extract even if content is unchanged |
| `pnpm pipeline --slugs s1,s2` | Run for specific fund slugs |
| `pnpm pipeline --step <name>` | Run one step |
| `pnpm pipeline:signals` | Filter + enrich only (no fetching) |
| `pnpm pipeline:signals-to-portfolio` | Convert deal/exit signals to portfolio entries |
| `pnpm audit:quality` | Fund data quality audit |

## Critical Rules

### 1. Caching — THE #1 BUG SOURCE
`data.ts` has module-level caches with **NO TTL and NO invalidation**. The worker writes JSON, so **restart `pnpm dev` to see changes**. The full cache list is in `apps/web/CLAUDE.md`.

### 2. Type Contract — NOT ENFORCED AT RUNTIME
Python writes dicts to JSON with no schema validation. TypeScript types are compile-time only. Known drift exists between Python output and TS declarations. **When you change a type**: update `types.ts`, the Python dicts and the `data.ts` loaders, then check that the JSON output matches.

### 3. Signal Dual-Loading
- `/signals` → `signals_unified.ts` → enriched → filtered → raw
- `/funds/[slug]` → `data.ts` → filtered ONLY
- Both share processing through `signalProcessing.ts`.
- After any filter, classification or text-cleaning fix, rerun **both** `filter_signals.py` and `enrich_signals_openai.py` (or `pnpm pipeline:signals`). `/signals` prefers `detected_signals_enriched.json`, so a fresh filtered file alone does not update the public feed.
- `filter_signals.py` has an incremental cache. It invalidates itself when the filter code, the shared signal-cleaning/correction code, `db.json` or the filter thresholds change. Use `--force-full` only to bypass reuse on purpose.
- Dedup logic is in 2 places: Python `filter_signals.py` and `signals_unified.ts`. Update both.
- Classification must match in **3 places**: Python `signal_patterns.py` + `signal_corrections.py` (shared by filter and enricher) AND TypeScript `signalProcessing.ts`.
- Text cleaning is shared through `signal_text_utils.py`. `clean_display_text()` is the single entry point for all signal text fields (title, what_changed, enriched_summary, diff_summary). Filter and enricher both import it.

### 4. Data Reliability Contract
Every signal MUST have `source_url`, `source_name`, `published_at` (if known) and `observed_at`. All enrichment must have a verifiable `{field}_source_url`. AI is a data collection aid, not a data source. Never store "ai_inferred" as a source. The public-facing version is `docs/reliability-contract.md`.

### 5. Model Policy
- **OpenAI**: the model is `OPENAI_MODEL` in `apps/worker/fundradar_worker/paths.py`. Always import it from there. NEVER use GPT-4o (it hallucinates too much).
- **Gemini**: the model is `GEMINI_MODEL` in the same file. Always import it from there. NEVER use `gemini-2.x`. NEVER use Flash-Lite variants for data enrichment: they trade accuracy for throughput.

### 6. File-Based Architecture
- All data is in JSON files. The worker writes to `data/derived/` with `safe_json_write()` (atomic).
- The web reads through `data.ts`. NEVER read JSON directly in components.
- Resolve paths with `getRepoRoot()`. NEVER hardcode absolute paths.
- NEVER `Read()` PEM PDFs. Use `pnpm worker:ingest`.

### 7. Scope
Italy-only funds. Keep solutions minimal. Avoid over-engineering.

### 8. Documentation
When you learn something non-obvious about the codebase (a subtle behavior, a pitfall, a bug root cause), write it into the one doc that owns that topic before you finish:

- `AGENTS.md` (this file) — cross-cutting rules, architecture patterns, pitfalls
- `apps/web/CLAUDE.md` — web behavior, dedup details, component logic
- `apps/worker/CLAUDE.md` — pipeline, patterns, signal classification details
- `docs/` — task guides; `docs/README.md` is the index

Other docs link to the owner doc. They do not repeat the fact.

**Docs contain timeless rules only, never changelog entries.** Git is the changelog. Forbidden: dated sections, date markers such as "(Mar 2026)" or "as of YYYY-MM", and change-history phrasing ("was removed", "was fixed", "previously X").

**Write the current rule, not what changed.** Bad: "Added `\bsale\b` to `_RE_EXIT_VERBS` (Mar 2026)." Good: "`_RE_EXIT_VERBS` includes the noun `\bsale\b`. Do not remove it, or 'sale of X' signals are not recognized as exits."

## Data Pipeline

### Source → Output → Loader

| Data | Output File | Web Loader |
|------|-------------|------------|
| Fund list | `db.json` | `getAllFunds()` |
| Deals | `pem_deals.json` | `getDealsForFund()` |
| Portfolios | `portfolio_items.json` | `getPortfolioForFund()` |
| Signals (filtered) | `detected_signals_filtered.json` | `getSignalsForFund()` |
| Signals (enriched) | `detected_signals_enriched.json` | `loadUnifiedSignals()` |
| Team stats | `linkedin/fund_people_stats.json` | `getTeamAnalyticsForFund()` |
| LinkedIn URLs | `linkedin/fund_linkedin_urls.json` | merged at load time |
| Fund coordinates | `fund_coordinates.json` (gitignored cache) | merged into `db.json` by `merge-aifi` |
| Unknown fund gaps | `unknown_fund_gaps.json` | worker dedup state only (not read by web) |

**10-step pipeline** (the step list is `STEPS` in `apps/worker/fundradar_worker/pipeline.py`; each step is described in `apps/worker/CLAUDE.md`):
`monitor → rss → translate (DeepL→Azure) → normalize_sectors → normalize_portfolio → enrich_portfolio (Gemini) → filter (quality scoring) → enrich (OpenAI summaries) → signal_to_portfolio (local) → enrich_portfolio_final (Gemini, second pass)`

`enrich_portfolio_final` (step 10) is an intentional second pass after `signal_to_portfolio` (step 9). Step 9 creates portfolio entries from deal/exit signals. Without step 10 those entries stay unenriched, and the pipeline always reports "remaining work".

**Translation order is CRITICAL**: `translate` runs at step 3, BEFORE `filter`. The filter uses English keyword patterns. Untranslated Italian signals score lower and get misclassified. The translation architecture is in `apps/worker/CLAUDE.md`.

Content hashing skips unchanged pages. Use `--force-extract` after you change an extractor. **The pipeline resumes after an interruption**: each step tracks progress in `data/derived/*_progress*.json`, and a new run continues from there.

**When signals have quality issues** (wrong type, missing, bad text, wrong fund, not in portfolio), use `docs/check_signals.md`. It lists each issue type and the function to edit.

### Address Data
`db.json` is the **only** source of address and coordinate data for the web app. `fund_coordinates.json` is a geocoding cache that only `merge-aifi-metrics.ts` reads. To update: `pnpm worker:geocode && pnpm merge-aifi`. The map resolution chain is in `apps/web/CLAUDE.md`.

## Architecture Patterns
- **Extraction**: fund-specific extractors take priority. Generic strategies run only when no custom extractor returns results.
- **Extractor URLS**: each extractor's `URLS` dict is the single source of truth for which URLs to fetch.
- **Entity resolution**: normalizes company names; fuzzy match at 90% Jaccard.
- **Atomic writes**: `safe_json_write()`. NEVER use bare `open()/json.dump()`.
- **Signal quality**: defense in depth. Python `filter_signals.py` is the primary gate; TS `signalProcessing.ts` is the safety net.
- **Signal shared modules**: `signal_patterns.py` (regex patterns), `signal_corrections.py` (type corrections + `detect_all_signal_types()`), `signal_text_utils.py` (text cleaning through `clean_display_text()`). Filter and enricher both use them.
- **Multi-type signals**: `signal_types?: SignalType[]` on `Signal` holds all types present in a signal (e.g. `["fundraise_closed", "exit_announced"]`), primary type first. Filter and enricher both write it through `detect_all_signal_types()`. `SignalCard.tsx` renders the extra types as secondary badges.
- **Unknown fund detection**: `fund_gap_detector.py` finds Italian-style fund names in signal text that are not in `db.json`. `alerting.py::send_unknown_fund_alerts()` sends them to Telegram only when `FUNDRADAR_TELEGRAM_BOT_TOKEN` and `FUNDRADAR_TELEGRAM_CHAT_ID` are set. Dedup state is in `data/derived/unknown_fund_gaps.json`.
- **Extractor vs pipeline boundary**: extractors handle site-specific HTML parsing and URL routing. The pipeline handles universal classification language (e.g. "takes a stake" → deal). Fund-specific metadata (e.g. ecosystem newsrooms) goes in `db.json`, not in pipeline code.
- **Fund metadata flags in db.json**: `is_ecosystem_newsroom` marks a newsroom that covers the whole market, not only the fund's own activity. `_is_misattributed_signal()` in `filter_signals.py` enforces it for ALL sources (RSS, web). To add a newsroom, set `"is_ecosystem_newsroom": true` in `db.json`. No code change is necessary.

## Key Files

| File | Role |
|------|------|
| `apps/web/src/lib/data.ts` | ALL data loading, module-level caches |
| `apps/web/src/lib/signals_unified.ts` | Signal loading for `/signals` |
| `apps/web/src/lib/signalProcessing.ts` | Shared signal processing (both paths) |
| `packages/shared/src/types.ts` | Type definitions (Fund, Signal, Deal, DataSource) |
| `apps/worker/fundradar_worker/pipeline.py` | Pipeline orchestration |
| `apps/worker/fundradar_worker/monitor.py` | Main fetch/extract/diff engine + exit detection |
| `apps/worker/fundradar_worker/translator.py` | Shared translation module (DeepL→Azure) |
| `apps/worker/scripts/filter_signals.py` | Primary quality gate (scoring, geo, dedup, reclassification) |
| `apps/worker/scripts/signal_patterns.py` | Single source of truth for shared regex patterns |
| `apps/worker/scripts/signal_corrections.py` | Shared post-classification corrections + `detect_all_signal_types()` |
| `apps/worker/scripts/signal_text_utils.py` | Shared text cleaning: `clean_display_text()`, `fix_spacing()`, `normalize_monetary_values()` |
| `apps/worker/scripts/signal_to_portfolio.py` | Signal → portfolio conversion (local) |
| `apps/worker/scripts/fund_gap_detector.py` | Detects unknown fund names in signal text |
| `apps/worker/fundradar_worker/strategies/extractors/` | Fund-specific extractors |

## Deployment (Vercel)

- **Vercel Root Directory**: `apps/web` (a Vercel project setting)
- **Config**: `apps/web/vercel.json`. The install and build commands move up to the repo root.
- **Static generation**: all fund pages are pre-rendered at build time by `generateStaticParams()`.
- **Dynamic OG image**: `opengraph-image.tsx` generates a 1200x630 PNG at the edge.
- **Read-only runtime**: the site serves committed JSON and writes nothing to the filesystem.
- **Data files**: committed to git in `data/` and `data/derived/`. `outputFileTracingIncludes` in `next.config.js` makes Vercel bundle them.
- **Base URL**: `src/lib/baseUrl.ts` returns `NEXT_PUBLIC_BASE_URL` if set, else `https://fundradar.vercel.app`. A fork on another domain must set `NEXT_PUBLIC_BASE_URL`.

### Data refresh workflow
1. Run `pnpm pipeline` locally to update data.
2. Commit the updated files in `data/derived/`.
3. Push. The Vercel project connected to the repo redeploys.

### Free, no accounts, no payments
There are no user accounts, subscriptions, payments or email digests. The site has no `/api` routes. Questions and data corrections go to GitHub Issues. Do not add account, payment or subscriber code.

## Common Pitfalls

Pitfalls that a sub-project doc covers in full point to it.

1. **Worker runs but UI shows old data** → restart `pnpm dev` (→ `apps/web/CLAUDE.md`).
2. **Adding subpage URLs to `data/monitor-urls.md`** → NEVER. The file holds base domain URLs only. Subpage routing is in the extractors' `URLS` dicts.
3. **Assuming fund website domains without checking AIFI** → verify URLs against `data/AIFI/all.csv`. AIFI is authoritative for member website URLs.
4. **AIFI scraper sets the wrong HQ for global funds** → it writes the Italian branch as HQ. After ANY AIFI merge, cross-check `offices[]` `is_hq` entries against the top-level `hq_*` fields. Keep the Italian office in `offices[]` when you fix the global HQ.
5. **Mentioning LinkedIn on the website** → NEVER use "LinkedIn" in user-facing text. Use "public profiles". Icon links are fine.
6. **Deleting global portfolio entries** → DON'T. The frontend filters by Italy with `isItalianCompany()`. Global data gives context.
7. **LinkedIn scraping** → on explicit request only, and never part of `pnpm pipeline`. It uses paid Apify credits. Rules: `docs/linkedin-scraping.md`.
8. **Career signals are valuable** → do NOT add career keywords to noise filters. The `job_posting` type is supported end to end.
9. **Wrong fund slugs** → ALWAYS look them up in `db.json`. Never guess (see the slug reference below).
10. **After an AIFI scrape** → check that names are brand names, not legal entity names. No `(Italia)`, no `Associati` suffix. `name` must match the fund's own website.
11. **AI is never disclosed in the UI** → never say a field is "AI-generated". Reference sources, not tools.
12. **No "as of" labels in the UI** → present data as current. If it is stale, update the data.
13. **Never delete enrichment progress or output files** → `signal_enrichment_progress.json` and `detected_signals_enriched.json` prevent paid re-translation and re-enrichment. Cost rules: `apps/worker/CLAUDE.md`. `enriched_summary` coverage below 100% is intentional: title-redundant summaries are cleared and the frontend shows the title.
14. **Fix the class, not the instance** → a direct edit of `detected_signals_*.json` costs nothing, but the next run brings the same problem back. Fix recurring issues in code (`docs/check_signals.md`). Use JSON edits only as a temporary patch or for a one-off backfill.
15. **NEVER remove or bypass the DeepL translation layer** → DeepL is the primary translator; Azure Translator is the fallback. OpenAI translation is disabled. Without DeepL and Azure, Italian text reaches the filter untranslated.
16. **NEVER move translation after the filter step** → `filter_signals.py` uses English keyword patterns (deal, exit, fundraise, etc.). Translation must run at step 3, before step 7. The enricher's translation pass is only a safety net.
17. **DeepL quota exhaustion** → `data/derived/deepl_quota_state.json` records exhausted keys, and the translator skips them. Delete the file to reset the state. When Telegram is configured, exhaustion of both keys sends an alert.
18. **Long-running scripts** → pipeline runs and Gemini audit/enrichment scripts can take minutes to hours. Run them in the background and watch their progress files. NEVER run two instances of the same script: they share progress files and corrupt each other.
19. **New sector tag in portfolio data breaks CI** → `sectorGroups.test.ts` scans all `portfolio_items.json` entries and fails on any unmapped sector tag. The root cause is almost always a scraper that passes a business description through as a sector. Fix the data at the source: (a) set the entry's sector to the correct canonical value, (b) add a length guard in the extractor (>50 chars or >5 words → `None`), (c) keep the `is_garbage_sector` threshold in `normalize_sectors.py` tight. **Do NOT add garbage sectors to `SECTOR_TAG_ALIASES`** — that hides the bug. Use `SECTOR_TAG_ALIASES` only for real sector labels with a different spelling (e.g. "fintech" → "Financial Services").
20. **Semantic dedup false positives in `signals_unified.ts`** → `DEDUP_STRUCTURAL_WORDS` strips fund-name slug words AND English stop-words before the word-overlap check. Without the stop-words, ecosystem newsroom funds (CDP Venture Capital, Itago), whose titles all start with the fund name, share many function words and get falsely deduped. **NEVER remove the English stop-words.** Details: `apps/web/CLAUDE.md`.
21. **`rebuild-gemini-audit-from-canonical.py` WIPES API run data** → it replaces `gemini_fund_asset_audit.json` from the canonical JSONL. API runs (`audit-fund-assets-gemini.py`) write directly to the output JSON and are **NOT** in the JSONL. Run the rebuild only when the output file is lost or corrupt. To add one manual import to an API audit: (1) `import-manual-gemini-fund-responses.py`, then (2) `audit-fund-assets-gemini.py --slugs <slug>` to merge. Never use rebuild as the merge step.
22. **`deal_amount` is often absent but extractable** → `_RE_EXTRACT_AMOUNT` in `filter_signals.py` fills the amount from title/what_changed at filter time. Do not add amount extraction to other steps.
23. **Cross-fund URL dedup is in the filter** → `_cross_fund_url_dedup()` in `filter_signals.py` runs after semantic dedup. It keeps only the highest-quality copy of a signal that matched several funds from the same source URL, and gives the winner a `co_fund_slugs` list. One copy with context is better than 3 copies.
24. **`portfolio_update` vs `deal_announced` for capex** → when a portfolio company invests in a plant, facility or production site, the type is `portfolio_update`. Pattern: `[Company] (FundName) invests €Xm for new [plant/facility/hub/...]`; the parenthetical fund name signals existing ownership. Wired in `correct_deal()` in `signal_corrections.py`.
25. **CI new-fund gate** → `scripts/check_new_fund_gate.py` runs when `db.json` or extractor files change. Funds already in `db.json` before the change are **established** and skip the strict completeness checks. Only new `db.json` entries get the full checks. A change set with new funds must include `data/derived/new_fund_completion_report.json` and `data/derived/gemini_fund_asset_audit.json` in its diff. Both files are gitignored, so add them with `git add -f`. The full workflow is in `docs/ADDING_A_FUND.md`.
26. **Italian signal titles slipping through the filter** → if `title_original` is absent (translation skipped), the filter subtracts 30 quality points when a short title (≤15 words) has 2+ Italian-specific words.
27. **Ecosystem newsroom signals from RSS aggregators** → signals from BeBeez or Il Sole 24 Ore attributed to an ecosystem newsroom fund (CDP VC, Itago, Faro Value) must contain the fund's distinctive slug keyword in title/what_changed. The check applies to all sources. A negative geo downgrade sets `italy_relevant=False` when the text names non-Italian EU geography (Bavaria, Munich, etc.) with no Italy mention and no relevance evidence. `signal_to_portfolio.py` skips `italy_relevant=False` signals.
28. **Responsive text variants** → render one variant conditionally (`{isMobile ? shortText : fullText}`). Do not render both and hide one with CSS classes. `FundsTable.tsx` has an `isMobile` state (`useEffect` + `matchMedia('(max-width: 768px)')`); reuse such state when it exists. Load heavy client libraries with `dynamic()` and `ssr: false`, as `TeamAnalyticsCharts.tsx` (Recharts) and `LeafletMap.tsx` (Leaflet) do.

Portfolio pitfalls (PEM merge, garbage entries, manual entries, status detection): `apps/web/CLAUDE.md`.
Extractor and worker pitfalls (force-extract, PortfolioStore guard): `apps/worker/CLAUDE.md`.

## Known Technical Debt

Intentional tradeoffs. Do not "fix" them without a clear reason:

- **data.ts is a large single file** — explicit and grep-friendly.
- **Portfolio merge mutates in place** — safe because the cache fills again on restart.
- **No runtime type validation** — JSON files are trusted.
- **Dedup logic in 2 places** — Python filter and `signals_unified.ts`, independently.
- **Team scoring is disabled in `fundQuality.ts`** — team data exists only for some funds.
- **PEM deal status needs verification** — reliable for deal existence, not for current status.
- **Signal importance is computed at runtime** — `getImportanceScore()` in `SignalsFeed.tsx` combines quality_score, evidence_score, type bonus, fund priority and Italy bonus. It is NOT stored in JSON. Do not add an `importance` field to the pipeline output.
- **enriched_summary is intentionally <100%** — title-redundant summaries are cleared (85% word overlap). The frontend falls back to the title.

## Fund Slug Reference

**CRITICAL: ALWAYS look up slugs in `db.json` — NEVER guess.** Old slugs resolve through `fund_aliases.json`.

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

GitHub holds every committed file. Gitignored files exist only in a local working copy, and `git clean -fdx` deletes them for good.

**Committed data**: `data/db.json`, `data/derived/portfolio_items.json`, `data/derived/company_profiles.json`, `data/derived/detected_signals*.json`, `data/derived/pem_deals.json`, `data/derived/linkedin/*.json`, `data/derived/signal_enrichment_progress.json`, `data/derived/gemini_fund_asset_zero_italy_verified.json`, and the other tracked files under `data/derived/`.

**Gitignored data** (a fresh clone does not have it):

| File / Pattern | Why gitignored | If lost |
|----------------|---------------|---------|
| `data/derived/linkedin/raw/` | Raw scraped profiles | Only a paid Apify re-scrape recreates it |
| `data/derived/gemini_fund_asset_audit*.json` | Large intermediate audit output | Rerun the audit; the derived whitelist is committed |
| `data/models/` | ML classifier joblib files | Retrain with `train_signal_classifier.py`; the filter uses rules only without them |
| `data/pem/*.pdf` | Large source PDFs | Needed only to re-ingest PEM; `pem_deals.json` is committed |

`signal_enrichment_progress.json` is committed as an exception to the `*_progress*` ignore rule. Without it, every signal is re-enriched through the paid API.

**Recovery rule for committed derived data**: if local `data/derived/` looks degraded but the files are committed, restore the last good version from git first. Then replay only the minimal current work. Keep `signal_enrichment_progress.json`, restore `portfolio_items.json` / `company_profiles.json` / `detected_signals_*.json` from git, and rerun free local steps such as `signal_to_portfolio` before any API rerun.

## Where to Start

1. Read `apps/web/CLAUDE.md` for the web app (caching, portfolio merge, signal loading).
2. Read `apps/worker/CLAUDE.md` for the worker (extractors, pipeline, status detection).
3. Read `docs/README.md` for the task guides (adding a fund, fixing signals, operations).
4. Run `pnpm install && pnpm dev` to check that the setup works.
