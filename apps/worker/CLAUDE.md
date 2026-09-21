# Worker — Agent and Contributor Notes

Project-wide rules are in the root `AGENTS.md`. This file owns the worker details.

## Architecture
Python 3.10+ worker. Fetches fund websites, extracts structured data, detects changes, and enriches signals. All output is JSON files in `data/derived/` consumed by the web app.

Key modules: core pipeline, fund-specific extractors (with URLS dicts), domain policies.

## Pipeline (10 steps)

> When signal quality is wrong — wrong type, missing signals, garbage passing through, text artifacts, portfolio not updated — see [`/docs/check_signals.md`](/docs/check_signals.md) for the full diagnostic and fix guide.

```
monitor → rss → translate → normalize_sectors → normalize_portfolio → enrich_portfolio (Gemini, optional) → filter → enrich (AI summaries + target_companies) → signal_to_portfolio (local) → enrich_portfolio_final (Gemini, optional)
```

1. **monitor** — Fetch pages via Playwright/requests, extract data using strategies, detect changes via diffing. Exit detection: companies removed from fund website are marked `status: "exited"` (not silently dropped). Signal-derived and Gemini-enriched entries are preserved unchanged.
2. **rss** — Fetch Italian news RSS feeds (BeBeez, FinanceCommunity, Il Sole 24 Ore, etc.), match articles to funds, append signals. Optional: skipped if no feeds configured.
3. **translate** (`translate_signals.py`) — **CRITICAL ORDER** — Translates Italian/French signal text to English with DeepL (primary) and Azure Translator (fallback). Writes back to `detected_signals.json` with originals in `*_original` fields. **Must run BEFORE filter** — filter patterns are English-language; Italian signals score lower and get misclassified. Optional: skips gracefully if no API keys, but quality degrades. Shared logic in `fundradar_worker/translator.py`.
4. **normalize_sectors** — Normalize fund + company sectors to canonical 30-sector taxonomy. `is_garbage_sector()` rejects: >50 chars with spaces, >5 words, known junk values. Unmapped sectors that survive are left as-is and reported — add a keyword to `SECTOR_KEYWORDS` to fix, or fix the extractor. **Real sector names are short** — the longest canonical is "Transportation & Logistics" (26 chars). Anything longer is a description that slipped through an extractor.
5. **normalize_portfolio** — Normalize company data across fund portfolios (names, dedup)
6. **enrich_portfolio** (`enrich_portfolio_gemini_full.py`) — Fill missing sector/HQ/description through Gemini (`GEMINI_MODEL`) with Google Search grounding. **Optional**: auto-skips if `GEMINI_API_KEY` not set. Capped at 50 API calls in pipeline mode.
7. **filter** (`filter_signals.py`) — Multi-gate quality pipeline, threshold at score >= 80 (configurable via `SIGNAL_MIN_QUALITY` env var):
   - Garbage detection (regex patterns), dedup (composite key + semantic 50% word overlap)
   - Misattribution detection (signals naming a different fund than tagged)
   - Italy-relevance gate: 3-tier fund classification (`italy_focused` / `europe_wide` / `mixed_or_global`)
   - ML classifier (optional, confidence-gated), event/conference reclassification
   - Signal types: deal, exit, fundraise, fund_launch, people_move, partnership, report, job_posting, debt_financing, portfolio_update
   - Title/text cleaning: ALL CAPS→title case, newspaper suffixes, date prefixes
   - Shared modules: imports patterns from `signal_patterns.py`, corrections from `signal_corrections.py`
   - Exit detection uses proper domain matching via `fund.get("website")` from db.json (not slug heuristics)
   - Ecosystem newsrooms flagged via `fund.get("is_ecosystem_newsroom")` in db.json (not hardcoded)
   - Incremental cache: warm runs reuse unchanged raw-signal fingerprints from `data/derived/signal_filter_progress.json` and fully rescore only new/changed raw signals. The cache auto-invalidates when filter code, shared signal-cleaning/correction code, `data/db.json`, or filter thresholds change. Use `python scripts/filter_signals.py --force-full` only when you intentionally want to bypass reuse.
8. **enrich** — AI summaries via OpenAI (only runs on filtered signals to control cost). Also extracts `target_companies` for deal/exit signals (used by step 9). The model is `OPENAI_MODEL` in `paths.py` (never GPT-4o). Contains a safety-net translation pass for any Italian that survived step 3 (e.g., LLM-generated Italian summaries). **enriched_summary coverage is intentionally <100%** — signals where the LLM summary is title-redundant (85%+ word overlap) get `enriched_summary=""` and the frontend falls back to displaying the title. This is correct behavior, not data loss. Progress tracking (`signal_enrichment_progress.json`) still marks them as processed, so re-runs skip them. **No keep/drop filtering** — the enricher does NOT drop signals; `filter_signals.py` (step 7) is the sole quality gate. The "done" marker is `enriched_at` (set on every processed signal).
   - The web feed prefers `detected_signals_enriched.json`. After any filter/classification/text-cleaning change, rerun step 8 as well so enriched output picks up the corrected `signal_type`, title, and summary fallback fields.
9. **signal_to_portfolio** (`signal_to_portfolio.py`) — Convert deal/exit signals into portfolio entries. **Purely local, zero API calls** — reads `target_companies` pre-extracted by step 8 (OpenAI enrichment). Trust hierarchy: fund press (0.90) > verified news (0.80) > news (0.75) > other (0.70) > rumor (0.60). Progress tracked to avoid re-processing. Also updates exit status for existing entries when exit signals match.
   - Reconciliation behavior: previously processed signals are automatically reprocessed when portfolio sync is still unresolved (investment target still missing or exit target not exited). This prevents progress-state drift.
   - Exit updates apply to entries with non-exited status (including `null`) and across normalized name variants.
   - Target company names are cleaned/validated with `portfolio_validation` before insert to block navigation/noise terms.
   - **Organizer fund routing** (`_find_organizer_slugs()`): for each deal signal, scans text for "organized/led/arranged by [Fund]" and "[Fund] organizes/leads [deal]" patterns. Matched funds are routed the signal with an `organizer_signal_ids` override: `is_direct_investment=True`, `action="investment"`. This fixes the structural gap where a fund organizing a club deal (= lead investor in Italian PE) was invisible to the pipeline because `fund_slug` pointed to a co-investor. Zero API calls — purely regex against fund names from db.json.
   - **Cross-portfolio KB normalization** (runs on EVERY execution, zero API calls): `build_company_knowledge_base()` builds a lookup of canonical sector/HQ/description/website from all portfolio entries. Used two ways: (a) gap-fill — fills any empty field from KB; (b) sector taxonomy upgrade — if an entry's existing sector is non-standard (not in 30-sector list) but KB canonical IS standard → overwrites. KB prefers taxonomy-standard sectors when building canonical. Description canonical = longest Gemini bio (non-signal-derived entries only). `check_portfolio_consistency()` runs after normalization and reports companies where existing values DISAGREE with KB canonical (capped at 10 in output, shows field, fund, actual value, canonical value). These conflicts require manual review — they are not auto-fixed to avoid overwriting intentional Gemini data.
   - **KB canonical selection quality**: sector is taxonomy-preferred, so Gemini values win. Description is the longest, so Gemini bios win. HQ is the most common value and ignores the source, so a stale scraped HQ can win when more funds carry it. A possible fix: prefer entries with `headquarters_source_url` in the HQ vote.
   - **`italy_relevant=False` guard**: signals with `italy_relevant=False` are skipped entirely for portfolio entry creation.
   - **Add-on acquisitions are NOT portfolio entries**: when `is_direct_investment=False`, the LLM determined a *portfolio company* (not the fund) made the acquisition. These signals must be classified as `portfolio_update`, NOT `deal_announced`. Do NOT try to add them to the portfolio — the fund did not make a new investment. If a signal is misclassified as `deal_announced` for an add-on, fix the classification in `signal_corrections.py` → `correct_deal()` using `_RE_PORTFOLIO_CO_AS_ACQUIRER`.

10. **enrich_portfolio_final** (`enrich_portfolio_gemini_full.py --pipeline`) — Second pass of portfolio enrichment, identical to step 6 but runs AFTER step 9. Necessary because `signal_to_portfolio` (step 9) creates new portfolio entries that step 6 could not have seen. Without this step, signal-derived portfolio entries (e.g. deal signals from today's RSS run) would always show as "remaining work" after every pipeline run. The enricher is progress-tracked so entries already processed in step 6 are skipped instantly. **`MAX_BATCH_ATTEMPTS = 3`**: if the Gemini API fails a batch 3 times, the entries are marked done anyway (with empty enrichment fields) so they don't block pipeline completion forever. The `enrichment_portfolio_full_progress.json` `"attempts"` dict tracks per-entry failure counts.

Run all: `pnpm pipeline`
Run filter+enrich only: `pnpm pipeline:signals`
Force re-extraction: `pnpm pipeline --force-extract`
Specific funds only: `pnpm pipeline --slugs f2i-sgr,triton --force-extract`
Signal→portfolio only: `pnpm pipeline:signals-to-portfolio` (standalone, with `--dry-run`, `--slugs`, `--force`)
Force a full signal refilter despite the incremental cache: `cd apps/worker && python scripts/filter_signals.py --force-full`

Each step: backs up output files → runs → validates output (exists, non-empty, valid JSON). Validation checks structure but **not schema** — an output of `{}` passes validation even if it should contain a `"signals"` key.

### Content Hash Optimization

The monitor tracks content hashes for each URL. If a website's HTML hasn't changed since the last fetch, extraction is **skipped** for efficiency — the previously extracted data in `portfolio_items.json` remains unchanged.

**When to use `--force-extract`:**
- After fixing or updating extractor code
- After fixing status detection logic in an extractor
- When you need to refresh all portfolio data regardless of content changes

Without `--force-extract`, updated extractor code won't take effect until the website's HTML actually changes.

## Output Files — What Goes Where

| Output File | Producer Module | Web Consumer |
|-------------|----------------|--------------|
| `db.json` | `merge-aifi-metrics.ts` (via `pnpm merge-aifi`) | `loadDatabase()` |
| `portfolio_items.json` | `monitor.py` + `signal_to_portfolio.py` | `getPortfolioForFund()` |
| `detected_signals.json` | `monitor.py` + `differ.py` + `rss_monitor.py` | (raw, not directly used by web) |
| `detected_signals_filtered.json` | `filter_signals.py` | `getSignalsForFund()`, `loadUnifiedSignals()` |
| `detected_signals_enriched.json` | `enrich_signals_openai.py` | `loadUnifiedSignals()` (preferred over filtered) |
| `pem_deals.json` | `ingest_pem.py` | `getDealsForFund()` |
| `aifi_members_enriched.json` | `aifi_scraper.py` | (merged into `db.json` via scripts) |
| `fund_people_stats.json` | `linkedin/*.py` | `getTeamAnalyticsForFund()` |
| `fund_aliases.json` | manual/generated | `slug_normalizer.py` (canonicalizes/blocks slugs) |
| `signal_to_portfolio_progress.json` | `signal_to_portfolio.py` | (progress tracking, not consumed by web) |
| `unknown_fund_gaps.json` | `fund_gap_detector.py` (called by `filter_signals.py`) | (worker-only dedup state, not consumed by web) |

## Critical Rules

### Atomic Writes — ALWAYS
Use `safe_json_write()` from `io_utils.py` (writes to temp file, then `os.replace`).
NEVER write JSON with bare `open()`/`json.dump()` — data corruption on crash.

### Backup Before Destructive Writes
Use `backup_before_write()` before overwriting critical files. Keeps 7 rotated backups.

### Career Postings Are Valuable Signals
Career postings are valuable signals — they indicate fund growth, new investment strategies, geographic expansion, and team scaling. Do NOT filter career/hiring signals as noise. Ensure career page content is extracted with full titles and descriptions.

### Sanitization — Use It But Don't Duplicate It
- `sanitize_text()`: strip HTML, remove control chars, normalize whitespace
- `sanitize_url()`: validate scheme, reject `javascript:`/`data:` URLs, encode spaces (`unquote(url).replace(" ", "%20")` — idempotent, prevents `%2520` double-encoding from spaces in href attributes)
- These live in `io_utils.py`. They are also called in `monitor.py` directly — be aware this sanitization happens in both places if modifying the pipeline

### Web App Cache — Your Writes Won't Show Up
The web app caches ALL data files in memory with no TTL. After any worker run, the user must restart `pnpm dev`. The worker does NOT notify the web server.

### Type Contract — Not Enforced
Python writes plain dicts to JSON. There is no schema validation — no jsonschema, no pydantic for output, no contract tests. TypeScript types in `packages/shared/src/types.ts` are the "intended" schema, but:
- Python writes fields TS doesn't declare: `snapshot_id`, `diff_summary`, `relevance_score`, `relevance_reasons`, `italy_relevant`, `extracted_entities`, `page_type`
- TS declares fields Python never writes: `data_source`, `verified`, `extraction_source`
- `fund_id` is written as empty string `""` — TS expects a real ID

**When adding/changing signal fields**: update the Python dict structure, update `types.ts`, and manually verify the JSON matches. There is no automated check.

## monitor.py — The God Module

This is the largest file. It combines:
- Orchestration (main monitoring loop)
- State management (SignalStore, NewsItemsStore, PortfolioStore classes)
- Signal classification and generation
- Graceful shutdown handling (GracefulShutdown class)

When working in this file, be aware of:
- Bare `except:` clauses that catch everything including SystemExit
- Exception handling inconsistency: some places log + continue, others swallow silently
- Heavy import section with optional try/except guards

## URL Configuration

All URL configuration is in each extractor's `URLS` dict. There are no per-site YAML configs. The monitor writes portfolio source URLs directly to `portfolio_items.json`.

## Extraction Strategies

### How Strategy Selection Works
`strategy_orchestrator.py` tries extraction in priority order:
1. Fund-specific extractor (`strategies/extractors/{fund}.py`) — highest confidence (0.95)
2. **If site-specific extractor returned results, generic strategies are SKIPPED** (prevents contamination)
3. Only if no site-specific extractor exists or it returned nothing: default strategy chain runs: NEXT_DATA → JSON_LD → HTML_CARDS → LOGO_GRID

Generic strategies are skipped when a custom extractor succeeds, because they often add garbage entries (navigation text, non-relevant companies from global portfolios, etc.).

Confidence scoring filters low-quality results (minimum 0.3).

### Portfolio Strategies
`next_data`, `nuxt_data`, `json_ld`, `html_cards`, `logo_grid`, `link_list`, `headings_in_context`, `table_rows`, `attributes`, `svg_titles`, `noscript`, `anchor_wrappers`

### Team Strategies
`team_cards`, `h3_with_title`, `json_ld_person`

### Fund-Specific Extractors
Custom extractors in `strategies/extractors/`. Each is a Python module that must export:
- `DOMAIN`: str — the domain this extractor handles (e.g., "www.permira.com")
- `URLS`: dict — paths to fetch for each page type: `{"portfolio": "/investments", "team": "/team", "news": None}`
- `EXTRACTORS`: dict — mapping of data_type to extractor function

The `URLS` dict is the **single source of truth** for which URLs to fetch. The monitor loads URLs from extractors by default via `url_generator.py`.

No interface enforcement — a malformed extractor fails silently (caught in monitor.py).

### Extractor URLS — MUST BE VERIFIED AGAINST LIVE SITE

Many extractors were auto-generated with template paths like `/investments`, `/management`, `/en/news`. These generic paths **do not exist** on most fund websites. Before committing an extractor:

1. **Always verify** each URL path returns 200 (use WebFetch or browser)
2. **Never use** template paths — check the actual website structure
3. **Common real paths**: `/portfolio/`, `/portafoglio/`, `/investimenti/`, `/our-companies/`, `/chi-siamo/`, `/team/`
4. **Single-page sites**: use `"/"` only if the homepage contains a real structured portfolio/team list
5. **No public portfolio index**: set `URLS["portfolio"] = None` and keep data manual/PEM-derived. Do **not** use homepage `"/"` as a placeholder; generic extraction will create sentence/news-title garbage companies.
6. **Check `url_status.json`** for known working paths for a domain (search by domain name)
7. **NEVER set URLS to None because the site is temporarily down.** A 500/503 does not mean the URL is wrong. Keep good URLs. Set `None` only when the page does not exist or is permanently removed.

A `# auto-generated from fund_urls.json` comment in a URLS block marks paths that may be unverified. After you check them, replace it with `# verified against live site`.

### When an Extractor Breaks or Doesn't Exist — Fallback Tools

Two libraries to reach for when a hand-written BeautifulSoup extractor breaks after a site redesign, or when a new fund has a complex/unusual page layout:

**[Scrapling](https://github.com/D4Vinci/Scrapling)** — drop-in BeautifulSoup replacement with **auto-match**: builds a structural fingerprint of an element and re-finds it even after the surrounding DOM changes. Use for:
- New extractors where you want resilience to future redesigns
- Existing extractors that keep breaking when the fund updates their site

**[LangExtract](https://github.com/google/langextract)** (Google) — structured extraction from **text** using LLMs (Gemini/OpenAI), with source grounding (every extraction maps back to its exact position in the source). Use when CSS/DOM-based extraction fails entirely:
1. Fetch the page, strip HTML to plain text (BeautifulSoup `.get_text()` or `sanitize_text()`)
2. Run LangExtract with a prompt + 1-2 examples of what a portfolio company entry looks like
3. Get structured `{name, sector, description}` dicts back
It can use `GEMINI_MODEL` from `paths.py` and the existing `GEMINI_API_KEY`. Neither library is a project dependency; add it to `pyproject.toml` if you use it. Most useful for: no-extractor funds, heavily JS-rendered sites after Playwright fetch, and pages where the structure is inconsistent.

### Portfolio Status Detection — CRITICAL

Portfolio entries must have a `status` field: `"current"`, `"exited"`, or `None` (unknown).

**Correct status logic by page type:**

| Page Type | Status Logic |
|-----------|--------------|
| Single-section portfolio page (e.g., `/portfolio`, `/investments`) | Default to `"current"` — page only shows active holdings |
| Dedicated exit page (e.g., `/realized`, `/prior-investments`) | Default to `"exited"` |
| Multi-section page (tabs, filters, labeled sections) | Use structural detection (see below) |
| Mixed page (no clear indicators) | Set to `None` — don't guess |

**Safe detection patterns (in priority order):**

1. **Data attributes** (best): `data-status="exited"`, `data-state="archived"`
2. **URL path**: `/current-portfolio/` vs `/prior-investments/`
3. **Parent element class/ID**: `#invest-cedute`, `.realised-portfolio`
4. **Section headers**: Track h2 headings like "Current" vs "Realised" in document order
5. **Labeled field values**: Check `Status:` label exists FIRST, then match value

**NEVER use these patterns:**
```python
# BAD - matches "exit" anywhere in text, causes false positives
if "exit" in description.lower():
    status = "exited"

# BAD - keyword matching on arbitrary text
if any(word in text for word in ["divested", "sold", "realized"]):
    status = "exited"
```

**Correct pattern for labeled fields:**
```python
# GOOD - only check keywords on explicitly labeled status field
status_label = item.select_one(".status-label")
if status_label and "status" in status_label.get_text().lower():
    value = item.select_one(".status-value").get_text().lower()
    if value in ("exited", "realized", "ceduto"):
        status = "exited"
    elif value in ("current", "active", "attivo"):
        status = "current"
```

**When in doubt, use `None`** — incorrect status is worse than unknown status.

## Entity Resolution (entity_resolver.py)

Normalizes company names for deduplication across sources:
- Strips legal suffixes (S.p.A., S.r.l., Ltd., Inc., etc.)
- Lowercases, trims whitespace
- Match chain: exact → alias → website domain → fuzzy (90% Jaccard threshold) → create new entity

**Note**: the web app has its own `normalizeCompanyName()` in `data.ts` for the portfolio merge — these two normalization functions are independent implementations. A name that matches in one may not match in the other.

## Reliability Patterns

| Module | Purpose |
|--------|---------|
| `circuit_breaker.py` | Per-domain failure tracking, prevents cascade failures |
| `rate_limiter.py` | Per-domain rate limits |
| `domain_policies.py` | Per-domain config (rate, headless requirement, etc.) |
| `normalizer.py` | Content normalization for clean diffs (strips noise) |
| `quality_monitor.py` | Extraction quality metrics |
| `health_report.py` | Overall system health reporting |

`io_utils.py` protects `data/derived/` against file-sync tools such as iCloud Drive that leave placeholders or numbered conflict copies such as `detected_signals 2.json`. `safe_json_write()` removes stale `.icloud` placeholders before atomic writes. `backup_before_write()` and the pipeline output validation move numbered copies back to the canonical filename. Do not change pipeline output paths to match numbered copies.

**Gitignored data is NOT in a fresh clone.** `data/models/` (retrain with `train_signal_classifier.py`), `data/derived/linkedin/raw/` (paid Apify re-scrape) and `data/pem/*.pdf` are gitignored. Their derived outputs (`linkedin/fund_people_stats.json`, `pem_deals.json`) are committed, so the website does not depend on them.

`pnpm pipeline` runs a preflight before any step. It stops when free disk space is critically low or when canonical pipeline files are missing or replaced by sync placeholders or conflict copies. It fails before any API spend instead of running in a state that can corrupt `data/derived/`.

The worker `.venv` is gitignored. Build it with `pip install -e ".[dev,ml]"`, then `python -m playwright install chromium`. The Playwright browser build must match the installed `playwright` version, or fetches fail with "Executable doesn't exist". If imports fail without a code change, rebuild the venv before you debug pipeline code. Disk-cleaner tools can delete the Playwright browser cache; reinstall the browser if that happens.

`data/db.json` is curated core data, not disposable worker state. If a pipeline/recovery session leaves `db.json` with a broad unrelated diff (for example mass `sector_tags` rewrites), treat that as a separate review item rather than bundling it into a worker recovery commit. Restore from git unless you can justify the content change.

When committed derived artifacts suddenly collapse in quality or coverage (for example portfolio enrichment backlog jumps from near-zero to thousands, or `portfolio_items.json` / `company_profiles.json` lose populated fields), compare against git before spending APIs. The default recovery path is: restore the last good committed artifact, preserve committed progress files like `signal_enrichment_progress.json`, then replay only the minimal local steps that are cheap or zero-cost (`signal_to_portfolio`, selective filter/enrich reruns). Do not reflexively rerun full historical enrichment when git already holds the last good state.

The monitor batch timeout is dynamic. It scales with per-domain sequential work and parallel worker waves, not a flat 300-second ceiling. If the batch timeout is reached, the monitor stops scheduling additional domain work, cancels queued domain tasks, and gives in-flight fetches one per-URL timeout window to drain before cleanup. This prevents teardown races against live Playwright loops.

## Module Organization

| Category | Modules |
|----------|---------|
| **Core** | `monitor.py`, `cli.py`, `pipeline.py`, `data_writer.py` |
| **Fetch** | `fetcher.py`, `playwright_fetcher.py`, `playwright_pool.py`, `detail_page_fetcher.py` |
| **Extract** | `site_extractor.py`, `site_config_schema.py`, `strategy_orchestrator.py`, `strategies/`, `extractors/` |
| **Diff** | `differ.py`, `portfolio_diff.py`, `baseline.py` |
| **Enrich** | `enrichment.py`, `relevance.py`, `noise_filter.py` |
| **Validate** | `portfolio_validation.py` (validates/cleans portfolio entries before writing) |
| **External** | `aifi_scraper.py`, `ingest_pem.py`, `linkedin/` |
| **Reliability** | `circuit_breaker.py`, `rate_limiter.py`, `health_report.py`, `quality_monitor.py` |
| **I/O** | `io_utils.py`, `normalizer.py`, `url_utils.py`, `url_generator.py`, `entity_resolver.py` |
| **Signal Pipeline** | `scripts/signal_patterns.py`, `scripts/signal_corrections.py`, `scripts/signal_text_utils.py`, `scripts/filter_signals.py`, `scripts/enrich_signals_openai.py`, `scripts/translate_signals.py`, `scripts/fund_gap_detector.py` |
| **ML Classifier** | `fundradar_worker/signal_classifier.py`, `fundradar_worker/signal_features.py`, `scripts/train_signal_classifier.py` |
| **Translation** | `fundradar_worker/translator.py` (shared DeepL→Azure→OpenAI module) |

### Shared Signal Modules (scripts/)

The signal classification pipeline uses 4 shared modules to prevent pattern drift:

| Module | Purpose | Consumers |
|--------|---------|-----------|
| `signal_patterns.py` | **Single source of truth** for compiled regex patterns, constants, utility functions | `filter_signals.py`, `enrich_signals_openai.py`, `signal_corrections.py`, `signal_text_utils.py` |
| `signal_corrections.py` | Shared post-classification corrections (`apply_universal_demotions()`, `apply_type_corrections()`) + multi-type detection (`detect_all_signal_types()`) | `filter_signals.py` (primary, runs after `_reclassify_signal_type()`), `enrich_signals_openai.py` (defense-in-depth) |
| `signal_text_utils.py` | Shared text cleaning: `clean_display_text()`, `fix_spacing()`, `normalize_monetary_values()`, `repair_token_splits()`, AUM boilerplate stripping | `filter_signals.py`, `enrich_signals_openai.py` |
| `translator.py` | Shared translation: language detection, DeepL quota management, Azure fallback, OpenAI fallback | `translate_signals.py` (pipeline step), `enrich_signals_openai.py` (safety net) |

**When adding a new pattern**: add it to `signal_patterns.py`. Both filter and enricher import from it.
**When adding a new text cleanup rule**: add it to `signal_text_utils.py` inside `clean_display_text()`. Applied uniformly to all text fields (title, what_changed, enriched_summary, diff_summary) in both filter and enricher.
**When adding a new correction rule**: add it to `signal_corrections.py`. Both filter and enricher import and call it directly. Do NOT add inline correction patterns to `_reclassify_signal_type()` in `filter_signals.py` — they won't be shared with the enricher.

### fund_gap_detector.py — Unknown Fund Detection

`detect_unknown_fund_mentions(signals, known_slugs)` in `scripts/fund_gap_detector.py` scans filtered signal text for Italian-style fund names (matching `[Proper Names] SGR/Venture Partners/etc.`) that are not in `known_slugs`. Called by `filter_signals.py` after writing `detected_signals_filtered.json`.

- Deduplicates against `data/derived/unknown_fund_gaps.json` (30-day window), so a known gap does not alert twice
- `send_unknown_fund_alerts()` in `fundradar_worker/alerting.py` sends the results to Telegram when `FUNDRADAR_TELEGRAM_BOT_TOKEN` and `FUNDRADAR_TELEGRAM_CHAT_ID` are set. Otherwise the pipeline log is the only output
- The whole block is wrapped in try/except — gap detection failures never block the filter output
- `unknown_fund_gaps.json` is worker state only, not consumed by web; safe to delete to reset the 30-day dedup window

**When adding a new signal type**: update `signal_patterns.py` (CORE_GEO_TYPES/CORE_QUALITY_TYPES), `signal_corrections.py`, `filter_signals.py`, `enrich_signals_openai.py`, `signalProcessing.ts`, `types.ts`, `SignalsFeed.tsx`. Then retrain the ML classifier (`python scripts/train_signal_classifier.py`) so the new type gets a passthrough mapping in `map_type_to_signal_type()`.

### signal_text_utils.py — Architecture Notes

`clean_display_text()` is a 7-stage pipeline. **Stage ordering is critical:**

1. **Early-exit rewrites (before stage 1)**: Portfolio title rewrites ("X added to Fund portfolio" → "Fund: new investment in X") run at the very top of `clean_display_text()`, matching against the raw original text. This preserves proper noun casing — if done inside later stages, `_cdt_normalize_casing` (stage 4) lowercases the generated string's proper nouns because it detects the high capitalization ratio and triggers title-case→sentence-case conversion.
2. Stages 1–7 run on all other signals.

`fix_spacing()` — the "strip leading numbered list artifacts" rule requires **period or closing paren** after the number: `^\d+[.)]\s+`. This prevents stripping fund names that start with a number (e.g., "21 Invest", "3i"). Do NOT weaken this to bare `^\d+\s+` again.

`correct_exit()` in `signal_corrections.py` — checks bond/debt patterns (`_RE_BOND_ISSUANCE`, `_RE_DEBT_FINANCING_BROAD`, `_RE_CREDIT_FACILITY`) before the general exit-verb checks. Bond/debt issuances would otherwise be mislabeled `exit_announced`.

`normalize_monetary_values()` — comma-formatted thousands (`€720,000`) are converted to compact notation (`€720K`, `€1.2M`) at the very beginning of the function, before all other rules. Pattern: `([€$£])\s*(\d{1,3}(?:,\d{3})+)(?!\s*[KMBT]|\d)`.

`_TITLE_CASE_ACRONYMS` — includes PE/finance terms: `LBO`, `MBO`, `NPL`, `SPAC`, `LP`, `GP`, `VC`, `PE`, `IRR`, `NAV`, `EV`, `SaaS`, `AI`, `ICT`, `B2B`, `B2C`, `SME`, `CVC`. The list restores correct casing after `.title()` lowercases them.

`apply_universal_demotions()` — includes a conference-event-with-date check: titles matching `\d+(st|nd|rd|th)?\s+annual\b.{0,80}\d{1,2}/\d{1,2}/\d{4}` are demoted to `other`. This catches conference listings like "3rd Annual LPGP Connect CFO/COO 3/25/2026 - Capital Dynamics" that lack the usual congress/summit keywords.

`apply_type_corrections()` `other` rescue — in addition to the existing "names/appoints X as role" rescue, a **standalone professional title** rescue fires when the title contains managing director / head of / chief * officer / etc. with no PE fund/investment language. Catches "Michele Romualdi managing director, Head of Investor Relations" type signals.

`correct_deal()` `_RE_REPORT` guard — the "strategic plan" pattern in `_RE_REPORT` matches incidental mentions like "in line with the Group's 2024–2026 Strategic Plan". The check has an `_RE_ACQUISITION_VERBS` title guard: if the TITLE has acquisition verbs, the report pattern in the body doesn't demote the signal. Without this, "X acquires Y (deal part of strategic plan)" → report. Do NOT remove the title guard.

`_reclassify_signal_type()` secured-loan check — `\bsecures?\b.{0,40}\b(?:loan|prestito)\b` in the TITLE bypasses the `_RE_BOND_EXCLUDE` guard that fires when speculative acquisition language appears elsewhere in the headline ("could this be a precursor to acquisitions?"). `_RE_BOND_EXCLUDE` includes `\bacqui\w+\b` which matches "acquisitions" from speculative questions. The title-only check is authoritative. There's also a matching post-ML guard in `filter_signals.py` since ML may still predict `deal_announced` from the "acquisitions" text.

`correct_deal()` / `correct_exit()` / `other` rescue — fund_launch rescue: when a signal contains explicit fund-launch verbs (`launches/lancia/nasce/avvia`) followed by a fund vehicle word within 80 chars, it is reclassified to `fund_launch` regardless of what type arrived. "TeamSystem Capital@Work launches FPAM 1 fund to invest in invoices" is a fund launch — the "invests in" describes the fund's mandate. This required fixes in 4 places:
1. `_RE_LAUNCH_FUND` / `_RE_FUND_LAUNCH_VERBS` in `signal_patterns.py` — uses `(?:es|ed)?` so conjugated forms (`launches`, `launched`) match `\blaunch\b`. Do not remove the conjugation suffix or "launches" will stop matching.
2. `correct_exit()` in `signal_corrections.py` — moved `_RE_LAUNCH_FUND` check BEFORE `_RE_INVEST_VERBS` check. ML often predicts `exit_announced` for PA-invoice signals; without this the invest-verbs → deal path fired first.
3. `correct_deal()` in `signal_corrections.py` — fund_launch rescue at end of `correct_deal()` (covers ML-predicted `deal_announced`).
4. `other` rescue in `apply_type_corrections()` — fund_launch check BEFORE `_RE_INVEST_VERBS → deal_announced` (covers rule-classified `other`).
5. `filter_signals.py` post-ML fund_launch block — added `and not has_fund_vehicle` guard to `elif _RE_INVEST_VERBS` so fund mandate language doesn't override a correctly-classified `fund_launch`.

`demoted_to_other_by_editorial` flag in `filter_signals.py` — set `True` when `apply_universal_demotions()` returns `"other"` (investor meetings, press reviews, call-for-applications, conference listings, etc.). Two guards rely on it: (1) the post-ML rescue block skips re-classification of intentionally-demoted signals, (2) the **final reconciliation** block (re-runs `apply_universal_demotions()` on the fully-cleaned text) skips re-promotion to `exit_announced`/`deal_announced` when this flag is set. Without guard (2), AI-generated `what_changed` text like "this is NOT a news item about... exit" contains the word "exit", which matches `_RE_STRONG_EXIT_VERBS` (`\bexits?\b`) and undoes the demotion. Guard prevents this false re-promotion.

`_reclassify_signal_type()` fund-as-acquirer check — when a signal is from the fund's own website domain and the title starts with "[Entity] acquires...", the code checks whether the entity is the fund itself. Uses **word-level matching** (`any(w in acquirer_name for w in fund_name_words)`), not substring match. Substring match fails when `fund_name = "emk capital"` and `acquirer_name = "emk"` — "emk capital" is not a substring of "emk" so it would wrongly return `exit_announced`. The word-level check correctly identifies "emk" as one of the fund name words and skips the exit reclassification. Only words ≥3 chars are used for matching.

`ITALY_MENTION_PATTERNS` and `clean_display_text()` CamelCase interaction — `clean_display_text()` splits CamelCase brand names into words ("WeAreProject" → "We Are Project"). Any pattern in `ITALY_MENTION_PATTERNS` that matches a CamelCase brand name must therefore include BOTH forms: the compact form (`\bWeAreProject\b`) AND the expanded form (`\bWe\s+Are\s+Project\b`). Without the expanded form, `_mentions_italy()` returns False after text cleaning, failing the Italy geo gate for `europe_wide` funds. Rule: whenever adding a CamelCase company name to `ITALY_MENTION_PATTERNS`, add a second pattern using `\s+` between the camel-humps.

`_cdt_normalize_casing()` person-name casing — two patterns for person names in appointment context:
1. **Forward** (line ~1447): `(appointed|...) [lowercase name]` → capitalizes the name after the verb.
2. **Reverse** (line ~1455): `[Capital first] [lowercase surname] (appointed|...)` → capitalizes the surname before the verb. Needed when the name precedes the verb (e.g. "Claudia pingue appointed").

`_cdt_normalize_casing()` small-word lowercasing — after all role-word capitalization rules, a regex lowercases articles/prepositions (`Of`, `And`, `Or`, `In`, `At`, `To`, `By`, `From`, `With`, `The`) when they sit between two title-cased words. Fixes "Head Of Fund" → "Head of Fund", "CEO And General Manager" → "CEO and General Manager". Safe to apply even when `_is_title_cased()` returns False (mixed-language titles from AI enrichment that bypass sentence-case conversion).


### Enricher "processed but missing" signals — Root Cause and Fix

**Symptom**: Signals in `processed_ids` in `signal_enrichment_progress.json` that are absent from `detected_signals_enriched.json`. Shows up as `signal_parity_missing_in_enriched` in CI gate reports.

**Root cause**: The enricher was run with `--slugs` flag for specific funds. The `_merge_output_signals()` function preserves non-target signals from the EXISTING enriched file. If the enriched file was subsequently regenerated (full pipeline run) without including those signals (e.g., they were newly filtered in after the enricher ran), they appear in `processed_ids` but not in the output.

**Fix pattern** (free, no API calls):
1. Copy the missing signals from `detected_signals_filtered.json` → `detected_signals_enriched.json` directly
2. Remove their IDs from `processed_ids` in `signal_enrichment_progress.json`
3. On next full pipeline run, the enricher will add proper LLM summaries to them

**Do NOT** re-run the enricher to fix this. It makes paid API calls; direct JSON edits are free.

### Enricher Token Budget — Reasoning Models

The configured OpenAI model is a reasoning model: it spends hidden reasoning tokens before visible output. With `max_completion_tokens=1024`, a complex signal can spend the whole budget on reasoning and return `finish_reason=length` with empty `message.content`. The enricher detects `finish_reason == "length"` on an empty response and retries with double the budget (1024 → 2048).

### Enricher Done/Progress Tracking

The enricher does NOT drop signals — `filter_signals.py` (step 7) is the sole quality gate. The "done" marker is `enriched_at` (set on every processed signal). The pipeline does not track "signals without decision" — if the enricher ran, all signals have been processed.

`_passes_strict_quality_gates()` in `filter_signals.py` — **noise gates run BEFORE the `italy_focused` early return**. This order is intentional: bare portfolio extraction signals (just a company name, no context) must be caught even for italy-focused funds that otherwise get a pass on geo checks.

`italy_relevant=True` reliability: the flag is trustworthy only when `relevance_score > 0` OR `relevance_reasons` is non-empty. A signal with `italy_relevant=True`, `relevance_score=0`, and no `relevance_reasons` means the flag was set as an upstream default — treat as unreliable. Non-italy-focused funds in this state fall through to text-based geo checks.

### ML Signal Classifier

The filter uses an optional sklearn ML classifier (`signal_classifier.py`) for confidence-gated type prediction and keep/discard scoring.

**Execution order** (critical — affects debugging):
1. Rule-based: `apply_universal_demotions()` → (if no demotion) `apply_type_corrections(original_type, ...)`
2. ML classifier runs next — when `type_confident=True`, ML overwrites the rule-based result unconditionally
3. Post-ML corrections: targeted fixes for a few types + a **post-ML rescue block** that re-applies `apply_type_corrections("other", ...)` for any signal ML set to "other"

**The ML can override rule-based corrections** — so the rule giving the correct type in step 1 may be silently reverted to "other" in step 2. The post-ML rescue block (step 3) guards against this for most cases.

**`demoted_to_other_by_editorial` flag**: when `apply_universal_demotions()` explicitly returned "other" (investor meetings, press reviews, call_for_applications, etc.), this flag is set `True` and the post-ML rescue is disabled — preventing re-classification of intentionally demoted signals. The **final reconciliation** block also re-runs `apply_universal_demotions()` — the flag prevents it from re-promoting the signal to exit/deal even when the full text contains exit/deal vocabulary in a negating context (e.g., AI-generated `what_changed`: "this is NOT a news item about... exit").

**To diagnose a signal that "corrections fix in isolation but stays other in output"**: run `apply_universal_demotions()` and `apply_type_corrections("other", ...)` on the text first. If corrections give the right type, the ML is overriding — check whether `demoted_to_other_by_editorial` should be False for this signal. See `docs/check_signals.md` Issue 20.

**Models** (in `data/models/`):

| File | Purpose |
|------|---------|
| `signal_vectorizer.joblib` | TF-IDF vectorizer (shared by both models, fitted on filtered signals) |
| `signal_type_model.joblib` | 11-class LogisticRegression for signal type |
| `signal_keep_model.joblib` | Binary LogisticRegression for keep/discard |
| `signal_feature_meta.json` | Metadata: labels, thresholds, train counts |

`data/models/` is gitignored, so a fresh clone has no model files. Without them the filter uses rule-based classification only. Train the models with the command below (needs the `ml` extra).

**Model design**:
- Algorithm: `LogisticRegression(class_weight='balanced', solver='lbfgs')` for TYPE; `liblinear` for KEEP
- TYPE: 11 classes, trained on the filtered signals (ground truth). Macro-F1 is low by design: small classes like `partnership`/`job_posting` rarely get confident predictions, and rule-based corrections handle them. `signal_feature_meta.json` records the training counts
- KEEP: trained on filtered signals (positive) against raw-minus-filtered signals (negative)
- Thresholds: keep ≥ 0.70, type ≥ 0.60 (stored in `signal_feature_meta.json`, override via `SIGNAL_ML_KEEP_THRESHOLD` / `SIGNAL_ML_TYPE_THRESHOLD` env vars)
- Features: TF-IDF (20k ngrams) + 18 engineered features (amount/date/keyword flags, page_category, italy_relevant, relevance_score)

**Type labels** (all 11 full-name, passthrough via `map_type_to_signal_type()`):
`deal_announced`, `exit_announced`, `fund_launch`, `people_move`, `job_posting`, `portfolio_update`, `fundraise_announced`, `fundraise_closed`, `debt_financing`, `partnership`, `other`

Old short-name labels (`deal`, `exit`, `fund`, `people`, `job`) are still mapped for backward compatibility with legacy `.pkl` models.

**To retrain** (after accumulating new filtered signals or adding new types):
```bash
cd apps/worker
python scripts/train_signal_classifier.py
# Optional flags:
# --keep-threshold 0.72  --type-threshold 0.60  --seed 42
```
Overwrites the 3 `.joblib` files and `signal_feature_meta.json`. No pipeline restart needed — `get_signal_classifier()` loads from disk on next filter run (module-level singleton, reset between pipeline runs).

**When NOT to retrain**: the ML classifier is confidence-gated. If `type_confident=False` the filter falls back to rule-based classification. Low macro-F1 on small classes is correct behavior — rules are the primary classification path for rare types.

### Portfolio Company Classification Rules

**CRITICAL**: `deal_announced` = fund deploys capital. `portfolio_update` = portfolio company acts.

#### Portfolio Company M&A (add-on acquisitions)

When a **portfolio company** makes an acquisition, it's **always `portfolio_update`** — the fund is not making a new investment, its existing portfolio company is growing via add-on M&A.

**Covered by `_RE_PORTFOLIO_CO_AS_ACQUIRER` in `signal_patterns.py`**:
- `[Fund]-backed [Company] acquires X` — hyphenated compound adjective
- `[Company], backed by [Fund], acquires X` — fund in non-principal position
- `portfolio company acquires X` — explicit portfolio language
- `bolt-on/add-on/tuck-in acquisition` — inherently portfolio company M&A
- Italian equivalents: `partecipata/sostenuta/controllata da ... acquis*`

**Classification wired in `correct_deal()` in `signal_corrections.py`** — fires before any deal-verb check, so acquisition verbs in the text don't prevent the reclassification. Both filter and enricher benefit automatically.

**Negatives (stay `deal_announced`)**:
- `[Fund] acquires [Company]` — fund is the subject, no "backed" modifier
- `[Fund]-backed acquisition of X` — "backed" modifies the abstract noun "acquisition", no company between backed and the verb

#### Portfolio Company Capex / Infrastructure Investments

When a **portfolio company** invests in a plant, production facility, manufacturing site, or infrastructure, it's **`portfolio_update`** — the fund already owns the company; this is capex, not a new acquisition.

**Pattern**: `[Company] (Fund) invests €Xm for new [plant/facility/hub/...]` — parenthetical fund attribution signals existing ownership.

**Classification wired in `correct_deal()` in `signal_corrections.py`** — fires at the end of `correct_deal()`, just before the final `return "deal_announced"`:
```python
# signals like "Kedrion Biopharma (Permira) invests €150M for new plasma fractionation plant"
# Position-aware: parenthetical must come BEFORE the capex keyword (fund attribution, not location)
if _is_capex:
    _paren_m = re.search(r"\([a-zA-Z][a-zA-Z\s&,]{1,29}\)", text_lower)
    if _paren_m:
        _after_paren = text_lower[_paren_m.end():]
        if re.search(r"\b(?:invest\w*|plant|facility|...)\b", _after_paren):
            return "portfolio_update"
```

**Position-aware check is critical**: `(Italy)` or `(Series B)` appearing AFTER the capex keywords are geographic/round qualifiers — not fund attribution. The fund attribution `(Permira)` always precedes the investment verb in real signal text. Using a simple parenthetical regex without position check would cause false positives (any text with location/round qualifiers in parens). **Also present in `apply_type_corrections()` `other` rescue block** for signals that arrive as `other`.

### Shared Utility Functions — NEVER Re-implement Inline

These utilities exist in `fundradar_worker/` and MUST be used instead of inline reimplementations:

| Utility | Module | Purpose | NEVER do this instead |
|---------|--------|---------|----------------------|
| `safe_json_write()` | `io_utils.py` | Atomic JSON write (tempfile + os.replace) | `tempfile.mkstemp()` + `os.replace()` inline, or local `save_json_atomic()` |
| `load_progress_file()` | `io_utils.py` | Load progress JSON with default fallback | `if path.exists(): json.load()` + `except` inline |
| `load_funds_by_slug()` | `io_utils.py` | Load db.json indexed by slug | Custom db.json loading per-script |
| `extract_domain()` | `url_utils.py` | Extract domain from URL (strips www by default) | `urlparse().netloc.replace("www.", "")` inline |
| `is_same_domain()` | `url_utils.py` | Compare two URLs/domains (ignoring www) | Inline domain extraction + `==` comparison |
| `MONTH_NAMES` | `date_utils.py` | Italian + English month name → zero-padded number (all forms: full, short, abbreviated) | Hardcoded `month_map` dict in each extractor/script |
| `SECTOR_TAXONOMY` | `paths.py` | Canonical 30-sector list | Redefining the list in each pipeline script |

The enricher uses `_apply_final_type_and_overrides()` as a single entry point for all post-classification corrections across its 3 code paths. NEVER duplicate correction + safety override logic inline.

### Fund Metadata Flags in db.json

Some filter behavior is controlled by fund-level metadata in db.json (not hardcoded in pipeline code):

| Flag | Purpose | Current Funds |
|------|---------|---------------|
| `is_ecosystem_newsroom` | Newsroom publishes market-wide news (not just own activity). Filter requires fund name in signal text. | `cdp-venture-capital`, `itago`, `faro-value` |

To add a new ecosystem newsroom: set `"is_ecosystem_newsroom": true` in the fund's db.json entry — no code changes needed.

### LinkedIn Modules (`linkedin/`)
`apify_client.py`, `batch_scraper.py`, `people_scraper.py`, `people_stats.py`, `post_classifier.py`, `posts_scraper.py`, `priority_ranker.py`, `process_manual_profiles.py`, `profile_classifier.py`

### LinkedIn Scraping Cadence

LinkedIn scraping is never part of `pnpm pipeline`. Run it only on explicit request, at most once per year per fund, because every run spends paid Apify credits. Commands, actor limits, raw-data protection and the source-of-truth rules are in [`docs/linkedin-scraping.md`](../../docs/linkedin-scraping.md).

## Adding a New Fund

1. **Create a custom extractor** in `strategies/extractors/{fund_name}.py`:
   ```python
   DOMAIN = "www.example-fund.com"  # Must match fund's website domain

   URLS = {
       "portfolio": "/investments",  # Path to portfolio page
       "team": "/team",              # Path to team page (or None)
       "news": "/news",              # Path to news page (or None)
   }

   def extract_portfolio(html: str, base_url: str) -> list[dict]:
       # Your extraction logic here
       ...

   EXTRACTORS = {
       "portfolio": extract_portfolio,
   }
   ```
2. Verify the fund exists in `db.json` with a matching `website` field (check against `data/AIFI/all.csv`)
3. Run `pnpm worker:monitor --slugs <fund-slug>` to test
4. Restart web dev server (`pnpm dev`) to see results

The full workflow, including data-quality gates, is in [`docs/ADDING_A_FUND.md`](../../docs/ADDING_A_FUND.md).

If the portfolio page is complex or the structure keeps changing: consider **Scrapling** (auto-match CSS selectors) or **LangExtract** (text → structured extraction via Gemini) instead of hand-writing BeautifulSoup selectors. See "When an Extractor Breaks or Doesn't Exist" above.

### Key Architecture Notes for Fund Setup

- **Custom extractors** (`strategies/extractors/{fund}.py`): Each has `DOMAIN`, `URLS`, and `EXTRACTORS`. The `URLS` dict is the **single source of truth** for which pages to fetch. The monitor reads URLs from extractors by default.
- **`url_generator.py`**: Reads `URLS` from all extractors and generates full URLs. Called by `monitor.py`.
- **Portfolio source URLs**: Written directly to `portfolio_items.json` alongside portfolio data when the monitor runs.
- **db.json website field**: Must match the AIFI source data in `data/AIFI/all.csv`. Verify against AIFI before changing.

### AIFI Name Cleaning (`aifi_scraper.py`)

AIFI registers members by legal entity name, not brand name. `clean_fund_name()` automatically cleans these for display and slug generation:

1. Strips branch suffixes: "- Italian Branch", "- Milan Branch", "- Succursale Italiana"
2. Strips parenthesized legal info: "(Luxembourg) S.A.", "(Ireland) Limited"
3. Strips foreign legal suffixes: SAS, SA, GmbH, LLP, LP
4. Strips trailing "Italy"/"Italia" (branch indicators)
5. Applies `AIFI_NAME_OVERRIDES` for known brand mismatches

The original AIFI name is preserved in `legal_name` field on the fund object.

**When to add an override**: If a fund's display name doesn't match what the fund calls itself on its website (check their homepage title and domain). Add to `AIFI_NAME_OVERRIDES` dict in `aifi_scraper.py`. Key = name after regex cleaning, value = correct brand name.

**Extractor filenames**: Named after the brand (e.g. `pai_partners.py`), loaded by `DOMAIN` attribute at runtime. The filename doesn't affect matching — only the `DOMAIN` constant matters.

## Adding a New Signal Field

This is error-prone because there's no schema enforcement:

1. Add the field to the signal dict in `monitor.py` (or wherever the signal is generated)
2. Add the field to `Signal` interface in `packages/shared/src/types.ts`
3. If the field should survive filtering: verify `noise_filter.py` passes it through
4. If the field should survive enrichment: verify `enrichment.py` preserves it
5. Update the web loader if needed (`data.ts` or `signals_unified.ts`)
6. Run the pipeline and manually inspect the output JSON to verify the field appears correctly
7. Restart `pnpm dev` and verify the web app uses it

## ⚠️ Translation Architecture — Read Before Touching Anything Translation-Related

### Why translation order is CRITICAL
The filter (`filter_signals.py`) uses **English-language keyword patterns** to classify and score signals. Italian signals hitting the filter:
- Score lower (keywords don't match Italian verbs)
- Get misclassified (e.g., `acquisisce` doesn't match English exit/deal patterns)
- May be incorrectly filtered out as noise

**Translation MUST happen at step 3 (before filter step 7).** The `translate_signals.py` pipeline step translates `detected_signals.json` in-place before filter ever runs.

### NEVER do any of these:
- **Remove or disable the `translate` pipeline step** — filter quality drops for every Italian-sourced signal
- **Move translation after filter** — same effect as removing it
- **Remove the DeepL SDK (`deepl` package)** — translation then depends on Azure alone

### Translation chain (never change this order)
1. `DEEPL_API_KEY` — primary key
2. `DEEPL_API_KEY_2` — secondary key (used when the primary is exhausted)
3. `AZURE_TRANSLATOR_KEY` — fallback key 1 (set `AZURE_TRANSLATOR_REGION` to the key's region)
4. `AZURE_TRANSLATOR_KEY_2` — fallback key 2

`data/derived/deepl_quota_state.json` records exhausted DeepL keys, and the translator skips them. When both DeepL keys are exhausted, Azure takes over, and an alert goes to Telegram if it is configured. An Azure auth or quota error disables that key for the current run, and the next Azure key takes over. OpenAI translation (`translate_text_with_openai()`) is a no-op.

### Idempotency — how re-translation is prevented
- `translate_signals.py` checks `title_original` / `what_changed_original`: if set and current text looks English → skip
- The enricher's merge loop restores `*_original` fields from the previous enriched file, so the safety-net pass in `enrich_signals_openai.py` also skips already-translated signals
- **DO NOT delete `detected_signals_enriched.json`** — it carries the `*_original` fields that prevent re-translation. Deleting it forces full re-translation of all Italian signals on the next enricher run.

A bug that re-translates on every enricher run spends the translation quota fast. Check idempotency after any change to translation code.

## ⚠️ OpenAI Cost Control — Read Before Running Enrichment

Signal enrichment (`pnpm pipeline:signals` or step 8 of `pnpm pipeline`) makes paid OpenAI API calls. Repeated runs during debugging add up fast.

### Rules
1. **NEVER delete `data/derived/signal_enrichment_progress.json`** — it tracks which signals have been enriched. Without it, every filtered signal is enriched again.
2. **NEVER delete `data/derived/detected_signals_enriched.json`** — it carries the `*_original` translation fields. Without it, every Italian signal is translated again on the next run.
3. **Before any `pnpm pipeline:signals` run**, check how many signals are already processed: `python3 -c "import json; d=json.load(open('data/derived/signal_enrichment_progress.json')); print(len(d.get('processed_ids',[])),'already processed')"`.
4. **For debugging and testing fixes**: edit `detected_signals_enriched.json` directly (free) instead of re-running the enricher. Then put the real fix in code.
5. **For testing new classification patterns**: run `pnpm pipeline:signals --slugs specific-fund` (one fund's signals only).
6. **enriched_summary < 100% is EXPECTED** — the enricher clears `enriched_summary` when it repeats the title (70% overlap before merge, 85% at finalization). The UI then shows the title. Progress still marks these signals as processed, so a re-run does not process them again.

## Testing

- Framework: pytest
- Location: `apps/worker/tests/`
- Fixtures: `tests/fixtures/`
- Run: `cd apps/worker && pytest`

### Signal Classification Test Suite

The signal classification logic has a dedicated three-file test suite:

| File | Purpose |
|------|---------|
| `tests/test_signal_patterns.py` | Unit tests for every regex pattern in `signal_patterns.py` |
| `tests/test_signal_corrections.py` | Unit tests for every correction function in `signal_corrections.py` |
| `tests/test_signal_classification.py` | **End-to-end living spec** — tests the full `apply_type_corrections()` contract |

**`test_signal_classification.py` is the canonical classification contract.** It covers:
- Portfolio company M&A: all 8 BeBeez parenthetical patterns, bolt-on/add-on, hyphenated-backed, Italian variants
- Deal vs exit disambiguation: evaluating/exploring a sale, completed sale, seller-side language
- Fundraise vs deal: final close, company rounds, ordinal investments
- People move: rescue from other, demotion of false positives
- Debt financing vs deal: bonds, credit facilities, restructuring agreements
- Universal demotions: press reviews, events, editorials, opinion
- Other → type rescue: over-demoted signals with clear type indicators
- **`TestFeb2026AuditRegressions`**: regression tests with exact signal IDs and expected classification outcomes

**When changing classification logic**: at least one test in this suite must break or a new test must be added. If nothing breaks, the change may be silently wrong.
