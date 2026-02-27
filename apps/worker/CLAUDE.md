# Worker — Claude Code Instructions

## Architecture
Python 3.10+ worker. Fetches fund websites, extracts structured data, detects changes, and enriches signals. All output is JSON files in `data/derived/` consumed by the web app.

Key modules: core pipeline, fund-specific extractors (with URLS dicts), domain policies.

## Pipeline (9 steps)

```
monitor → rss → translate → normalize_sectors → normalize_portfolio → enrich_portfolio (Gemini, optional) → filter → enrich (AI summaries + target_companies) → signal_to_portfolio (local)
```

1. **monitor** — Fetch pages via Playwright/requests, extract data using strategies, detect changes via diffing. Exit detection: companies removed from fund website are marked `status: "exited"` (not silently dropped). Signal-derived and Gemini-enriched entries are preserved unchanged.
2. **rss** — Fetch Italian news RSS feeds (BeBeez, FinanceCommunity, Il Sole 24 Ore, etc.), match articles to funds, append signals. Optional: skipped if no feeds configured.
3. **translate** (`translate_signals.py`) — **CRITICAL ORDER** — Translates Italian/French signal text to English using DeepL (primary, 500K chars/month free × 2 keys) with OpenAI fallback. Writes back to `detected_signals.json` with originals in `*_original` fields. **Must run BEFORE filter** — filter patterns are English-language; Italian signals score lower and get misclassified. Optional: skips gracefully if no API keys, but quality degrades. Shared logic in `fundradar_worker/translator.py`.
4. **normalize_sectors** — Normalize fund + company sectors to canonical 30-sector taxonomy
5. **normalize_portfolio** — Normalize company data across fund portfolios (names, dedup)
6. **enrich_portfolio** (`enrich_portfolio_gemini_full.py`) — Fill missing sector/HQ/description via Gemini 3 Flash with Google Search grounding. **Optional**: auto-skips if `GEMINI_API_KEY` not set. Capped at 50 API calls in pipeline mode.
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
8. **enrich** — AI summaries via OpenAI (only runs on filtered signals to control cost). Also extracts `target_companies` for deal/exit signals (used by step 9). **DO NOT use ChatGPT 4o** — it hallucinates too frequently. Use `gpt-5-mini` or better. Contains a safety-net translation pass for any Italian that survived step 3 (e.g., LLM-generated Italian summaries). **enriched_summary coverage is intentionally <100%** — signals where the LLM summary is title-redundant (85%+ word overlap) get `enriched_summary=""` and the frontend falls back to displaying the title. This is correct behavior, not data loss. Progress tracking (`signal_enrichment_progress.json`) still marks them as processed, so re-runs skip them.
9. **signal_to_portfolio** (`signal_to_portfolio.py`) — Convert deal/exit signals into portfolio entries. **Purely local, zero API calls** — reads `target_companies` pre-extracted by step 8 (OpenAI enrichment). Trust hierarchy: fund press (0.90) > verified news (0.80) > news (0.75) > other (0.70) > rumor (0.60). Progress tracked to avoid re-processing. Also updates exit status for existing entries when exit signals match.
   - Reconciliation behavior: previously processed signals are automatically reprocessed when portfolio sync is still unresolved (investment target still missing or exit target not exited). This prevents progress-state drift.
   - Exit updates apply to entries with non-exited status (including `null`) and across normalized name variants.
   - Target company names are cleaned/validated with `portfolio_validation` before insert to block navigation/noise terms.

Run all: `pnpm pipeline`
Run filter+enrich only: `pnpm pipeline:signals`
Force re-extraction: `pnpm pipeline --force-extract`
Specific funds only: `pnpm pipeline --slugs f2i-sgr,triton --force-extract`
Signal→portfolio only: `pnpm pipeline:signals-to-portfolio` (standalone, with `--dry-run`, `--slugs`, `--force`)

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
- `sanitize_url()`: validate scheme, reject `javascript:`/`data:` URLs
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

## Site Configurations — DELETED

The YAML files that were in `data/site_configs/` have been archived to `archive/deprecated/site_configs/`. They are no longer used by any code. All URL configuration now lives in each extractor's `URLS` dict. The monitor writes portfolio source URLs directly to `portfolio_items.json`.

## Extraction Strategies

### How Strategy Selection Works
`strategy_orchestrator.py` tries extraction in priority order:
1. Fund-specific extractor (`strategies/extractors/{fund}.py`) — highest confidence (0.95)
2. **If site-specific extractor returned results, generic strategies are SKIPPED** (prevents contamination)
3. Only if no site-specific extractor exists or it returned nothing: default strategy chain runs: NEXT_DATA → JSON_LD → HTML_CARDS → LOGO_GRID

Generic strategies are skipped when a custom extractor succeeds because they often add garbage entries (navigation text, non-relevant companies from global portfolios, etc.). This was the primary source of portfolio data quality issues.

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

The `# auto-generated from fund_urls.json` comment in URLS blocks indicates paths that may not have been verified. Replace with `# verified against live site` after checking.

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

- Deduplicates against `data/derived/unknown_fund_gaps.json` (30-day window) — no duplicate Telegram alerts for already-known gaps
- Results sent via `send_unknown_fund_alerts()` in `fundradar_worker/alerting.py`
- The whole block is wrapped in try/except — gap detection failures never block the filter output
- `unknown_fund_gaps.json` is worker state only, not consumed by web; safe to delete to reset the 30-day dedup window
**When adding a new signal type**: update `signal_patterns.py` (CORE_GEO_TYPES/CORE_QUALITY_TYPES), `signal_corrections.py`, `filter_signals.py`, `enrich_signals_openai.py`, `signalProcessing.ts`, `types.ts`, `SignalsFeed.tsx`. Then retrain the ML classifier (`python scripts/train_signal_classifier.py`) so the new type gets a passthrough mapping in `map_type_to_signal_type()`.

### signal_text_utils.py — Architecture Notes

`clean_display_text()` is a 7-stage pipeline. **Stage ordering is critical:**

1. **Early-exit rewrites (before stage 1)**: Portfolio title rewrites ("X added to Fund portfolio" → "Fund: new investment in X") run at the very top of `clean_display_text()`, matching against the raw original text. This preserves proper noun casing — if done inside later stages, `_cdt_normalize_casing` (stage 4) lowercases the generated string's proper nouns because it detects the high capitalization ratio and triggers title-case→sentence-case conversion.
2. Stages 1–7 run on all other signals.

`fix_spacing()` — the "strip leading numbered list artifacts" rule requires **period or closing paren** after the number: `^\d+[.)]\s+`. This prevents stripping fund names that start with a number (e.g., "21 Invest", "3i"). Do NOT weaken this to bare `^\d+\s+` again.

`correct_exit()` in `signal_corrections.py` — checks bond/debt patterns (`_RE_BOND_ISSUANCE`, `_RE_DEBT_FINANCING_BROAD`, `_RE_CREDIT_FACILITY`) before the general exit-verb checks. Bond/debt issuances were being mislabeled `exit_announced` before this was added (Feb 2026).

`normalize_monetary_values()` — comma-formatted thousands (`€720,000`) are converted to compact notation (`€720K`, `€1.2M`) at the very beginning of the function, before all other rules. Pattern: `([€$£])\s*(\d{1,3}(?:,\d{3})+)(?!\s*[KMBT]|\d)`.

`_TITLE_CASE_ACRONYMS` — expanded (Feb 2026) to include PE/finance terms: `LBO`, `MBO`, `NPL`, `SPAC`, `LP`, `GP`, `VC`, `PE`, `IRR`, `NAV`, `EV`, `SaaS`, `AI`, `ICT`, `B2B`, `B2C`, `SME`, `CVC`. The list restores correct casing after `.title()` lowercases them.

`apply_universal_demotions()` — includes a conference-event-with-date check: titles matching `\d+(st|nd|rd|th)?\s+annual\b.{0,80}\d{1,2}/\d{1,2}/\d{4}` are demoted to `other`. This catches conference listings like "3rd Annual LPGP Connect CFO/COO 3/25/2026 - Capital Dynamics" that lack the usual congress/summit keywords.

`apply_type_corrections()` `other` rescue — in addition to the existing "names/appoints X as role" rescue, a **standalone professional title** rescue fires when the title contains managing director / head of / chief * officer / etc. with no PE fund/investment language. Catches "Michele Romualdi managing director, Head of Investor Relations" type signals.

`correct_deal()` fund_launch rescue (Feb 2026) — when a `deal_announced` signal contains explicit fund-launch verbs (`launches/lancia/nasce/avvia`) followed by a fund vehicle word (`fund/fondo/comparto/vehicle`) within 80 chars, it is reclassified to `fund_launch`. This prevents "TeamSystem Capital@Work launches FPAM 1 fund to invest in invoices" from being tagged as a deal (the "invests in" describes the fund's mandate, not an investment transaction). Runs AFTER the fundraise-closing checks so `fundraise_closed` signals are correctly handled first.

`_cdt_normalize_casing()` person-name casing (Feb 2026) — two patterns for person names in appointment context:
1. **Forward** (line ~1447): `(appointed|...) [lowercase name]` → capitalizes the name after the verb.
2. **Reverse** (line ~1455): `[Capital first] [lowercase surname] (appointed|...)` → capitalizes the surname before the verb. Needed when the name precedes the verb (e.g. "Claudia pingue appointed").

`_cdt_normalize_casing()` small-word lowercasing (Feb 2026) — after all role-word capitalization rules, a regex lowercases articles/prepositions (`Of`, `And`, `Or`, `In`, `At`, `To`, `By`, `From`, `With`, `The`) when they sit between two title-cased words. Fixes "Head Of Fund" → "Head of Fund", "CEO And General Manager" → "CEO and General Manager". Safe to apply even when `_is_title_cased()` returns False (mixed-language titles from AI enrichment that bypass sentence-case conversion).

`_passes_strict_quality_gates()` in `filter_signals.py` — **noise gates run BEFORE the `italy_focused` early return**. This order is intentional: bare portfolio extraction signals (just a company name, no context) must be caught even for italy-focused funds that otherwise get a pass on geo checks.

`italy_relevant=True` reliability: the flag is trustworthy only when `relevance_score > 0` OR `relevance_reasons` is non-empty. A signal with `italy_relevant=True`, `relevance_score=0`, and no `relevance_reasons` means the flag was set as an upstream default — treat as unreliable. Non-italy-focused funds in this state fall through to text-based geo checks.

### ML Signal Classifier

The filter uses an optional sklearn ML classifier (`signal_classifier.py`) for confidence-gated type prediction and keep/discard scoring. It is a secondary layer — rule-based corrections in `signal_corrections.py` always run after ML and can override its output.

**Models** (in `data/models/`):

| File | Purpose |
|------|---------|
| `signal_vectorizer.joblib` | TF-IDF vectorizer (shared by both models, fitted on filtered signals) |
| `signal_type_model.joblib` | 11-class LogisticRegression for signal type |
| `signal_keep_model.joblib` | Binary LogisticRegression for keep/discard |
| `signal_feature_meta.json` | Metadata: labels, thresholds, train counts |

**Current model (retrained Feb 2026)**:
- Algorithm: `LogisticRegression(class_weight='balanced', solver='lbfgs')` for TYPE; `liblinear` for KEEP
- TYPE: 11 classes, trained on 337 filtered signals (ground truth). Test macro-F1: ~0.43 (expected — small classes like `partnership`/`job_posting` won't produce confident predictions; rule-based corrections handle them)
- KEEP: trained on 337 pos + 1,668 neg signals (raw minus filtered). Test keep-F1: ~0.75, accuracy 0.90
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

### Portfolio Company M&A Classification Rule

**CRITICAL**: `deal_announced` = fund deploys capital. `portfolio_update` = portfolio company acts.

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

### Shared Utility Functions — NEVER Re-implement Inline

These utilities exist in `fundradar_worker/` and MUST be used instead of inline reimplementations:

| Utility | Module | Purpose | NEVER do this instead |
|---------|--------|---------|----------------------|
| `safe_json_write()` | `io_utils.py` | Atomic JSON write (tempfile + os.replace) | `tempfile.mkstemp()` + `os.replace()` inline |
| `load_progress_file()` | `io_utils.py` | Load progress JSON with default fallback | `if path.exists(): json.load()` + `except` inline |
| `load_funds_by_slug()` | `io_utils.py` | Load db.json indexed by slug | Custom db.json loading per-script |
| `extract_domain()` | `url_utils.py` | Extract domain from URL (strips www by default) | `urlparse().netloc.replace("www.", "")` inline |
| `is_same_domain()` | `url_utils.py` | Compare two URLs/domains (ignoring www) | Inline domain extraction + `==` comparison |

The enricher uses `_apply_final_type_and_overrides()` as a single entry point for all post-classification corrections across its 3 code paths. NEVER duplicate correction + safety override logic inline.

### Fund Metadata Flags in db.json

Some filter behavior is controlled by fund-level metadata in db.json (not hardcoded in pipeline code):

| Flag | Purpose | Current Funds |
|------|---------|---------------|
| `is_ecosystem_newsroom` | Newsroom publishes market-wide news (not just own activity). Filter requires fund name in signal text. | `cdp-venture-capital`, `itago`, `faro-value` |

To add a new ecosystem newsroom: set `"is_ecosystem_newsroom": true` in the fund's db.json entry — no code changes needed.

### LinkedIn Modules (`linkedin/`)
`apify_client.py`, `batch_scraper.py`, `people_scraper.py`, `people_stats.py`, `post_classifier.py`, `posts_scraper.py`, `priority_ranker.py`, `profile_classifier.py`

### LinkedIn Source-of-Truth Clarification

- `batch_scraper.py` `MEGA_FUNDS_TO_SKIP` only controls which global funds are skipped for automated LinkedIn employee scraping.
- `data/derived/linkedin/manual_profiles.json` is the source of truth for funds covered via manually curated LinkedIn profile links.
- Do not infer manual profile coverage from mega-fund skip sets.

### LinkedIn Scraping Cadence

People data does not need frequent refreshing — professionals change jobs infrequently, so **once a year per fund is sufficient**. Target Italian domestic/mid-size funds first — their small teams mean 25 profiles ≈ full coverage with 100% Italy relevance. Mega-funds in `MEGA_FUNDS_TO_SKIP` and `FOREIGN_FUNDS_TO_SKIP` are handled via `manual_profiles.json` (free, title-based classification) and do not use Apify budget.

### ⚠️ HarvestAPI Actor Limits (as of Feb 2026)

The `harvestapi/linkedin-company-employees` actor (updated Feb 14 2026) has **two separate limit systems**:

1. **Apify platform**: $5/month free credit. At $0.008/full profile, $5 = 625 profiles (~25 funds at 25 profiles each).
2. **Actor-level**: HarvestAPI limits **free Apify plan users to 10 runs/month**. Runs beyond 10 return 0 profiles with log message "Free users are limited to 10 runs."

**This means: max 10 funds per month, not 25.** The actual Apify cost for 10 funds at 25 profiles = $2.00 (well within $5 budget — the run limit is the real constraint, not money).

**Monthly run command (do not test — every run counts):**
```bash
cd apps/worker
APIFY_API_TOKEN=... python3 -m fundradar_worker.linkedin.batch_scraper \
  --max-employees 25 \
  --max-cost 2.50 \
  --delay 180
```

This runs ~10 funds (at $0.20 each), with 3-minute delays between funds to avoid LinkedIn rate limiting. The `--delay 180` is critical — rapid-fire runs also get blocked by LinkedIn's hourly rate limiter even within the 10-run allowance.

**If 0 profiles are returned:** Either the 10-run monthly limit is hit, or LinkedIn rate limiting (hourly reset). Check the Apify run logs — if you see "free user run limit exceeded" wait until the 1st of next month. If no such message, wait 1-2 hours and retry.

**Reset on the 1st of each month.** Don't test — every HarvestAPI run consumes Apify compute credits (actor startup cost) even if it returns 0 profiles. Testing burned the entire $5 free credit in Feb 2026. Wait for the monthly reset and run production directly.

### ⚠️ CRITICAL: LinkedIn Raw Data Protection

The scraped LinkedIn data in `data/derived/linkedin/raw/` is **irreplaceable** without spending Apify credits. **NEVER** run any script that could delete or overwrite these files:

| File Pattern | Count | Contents | Protection |
|-------------|-------|----------|------------|
| `raw/*_employees.json` | ~90+ | **Full profiles** from HarvestAPI: education, experience, skills | **NEVER overwrite** |
| `raw/*_enriched_profiles.json` | ~10 | Full career history (Apify supreme_coder profile scraper) | **NEVER overwrite** |
| `manual_profiles.json` | 1 | Manually curated mega-fund profiles | **NEVER overwrite** |

**IMPORTANT — HarvestAPI employee files are RICH data.** They contain full education (schoolName, degree, fieldOfStudy), full experience (position, companyName, startDate, endDate), skills, languages, etc. They are NOT headline-only. Always parse them with `harvestapi_to_profile()` from `people_stats.py` — NEVER create synthetic single-experience profiles from them.

**Enriched profile funds** (Apify supreme_coder format, slightly different structure): apollo, ares-management, blackstone, carlyle, eqt, kkr, macquarie-mam, permira-associati, towerbrook.

**Safe operations:**
- `process_manual_profiles.py --basic` — re-classifies from local files, merges into `fund_people_stats.json` (safe)
- Any script that only READS from `raw/` and WRITES to `fund_people_stats.json` (safe)
- Regenerating `fund_people_stats.json` from raw data (safe — derived, not source)

**NEVER run:**
- `batch_scraper.py` without explicit user approval (costs money, limited runs)
- `process_manual_profiles.py --enrich` without explicit user approval (calls Apify)
- Any script that writes to `raw/` directory or `manual_profiles.json`

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
3. Run `pnpm worker:monitor --limit 1` to test
4. Restart web dev server (`pnpm dev`) to see results

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
- **Remove or disable the `translate` pipeline step** — filter quality immediately degrades for ~60% of signals (Italian-sourced ones)
- **Move translation after filter** — same effect as removing it
- **Replace DeepL with OpenAI for bulk translation** — DeepL is ~50× cheaper and 10× faster. OpenAI translation costs ~$0.10/run. DeepL costs ~$0.001/run.
- **Remove the DeepL SDK (`deepl` package)** — the fallback to OpenAI works but burns money

### Translation chain (never change this order)
1. `DEEPL_API_KEY` — primary key (500K chars/month free)
2. `DEEPL_API_KEY_2` — secondary key (auto-failover when primary exhausted)
3. `AZURE_TRANSLATOR_KEY` — second fallback (2M chars/month free, region: `italynorth`)
4. OpenAI `gpt-5-mini` — last resort fallback (paid, ~$0.10/run for all Italian signals)

DeepL exhausted keys are auto-skipped via `data/derived/deepl_quota_state.json`. Both DeepL keys exhausted → Telegram alert fires + Azure takes over. Azure auth/quota errors disable it for the current run and fall through to OpenAI. Monthly quotas reset on the 1st.

### Idempotency — how re-translation is prevented
- `translate_signals.py` checks `title_original` / `what_changed_original`: if set and current text looks English → skip
- The enricher's merge loop restores `*_original` fields from the previous enriched file, so the safety-net pass in `enrich_signals_openai.py` also skips already-translated signals
- **DO NOT delete `detected_signals_enriched.json`** — it carries the `*_original` fields that prevent re-translation. Deleting it forces full re-translation of all Italian signals on the next enricher run.

### History: how we learned this the hard way (Feb 2026)
DeepL was removed thinking "OpenAI is a better translator". What actually happened:
1. OpenAI now did translation + enrichment, costing ~$0.30/run instead of ~$0.05/run
2. A merge loop bug caused the enricher to re-translate ALL Italian signals on EVERY run (not just new ones)
3. 50 debug runs × $0.30 = ~$15 in one session
4. Filter quality dropped because Italian signals arrived untranslated at the filter step
5. Full re-integration took a full day to restore signal quality

**Result**: DeepL re-added as step 3, translation moved before filter, merge loop fixed, `translator.py` module created as shared infrastructure.

## ⚠️ OpenAI Cost Control — Read Before Running Enrichment

Signal enrichment (`pnpm pipeline:signals` or step 8 of `pnpm pipeline`) makes OpenAI API calls. Misuse can cost $10–$20 in a single debugging session.

### Rules
1. **NEVER delete `data/derived/signal_enrichment_progress.json`** — it tracks which signals have been LLM-enriched. Deleting it forces full re-enrichment of all filtered signals (~$2–5).
2. **NEVER delete `data/derived/detected_signals_enriched.json`** — it carries `*_original` translation fields. Deleting it forces re-translation of all Italian signals on the next run.
3. **Before any `pnpm pipeline:signals` run**, check how many signals would be affected: `python3 -c "import json; d=json.load(open('data/derived/signal_enrichment_progress.json')); print(len(d.get('processed_ids',[])),'already processed')"`.
4. **For debugging/testing fixes**: edit `detected_signals_enriched.json` directly (free) instead of re-running the enricher.
5. **For testing new classification patterns**: run `pnpm pipeline:signals --slugs specific-fund` (processes one fund's signals only).
6. **Re-enrichment costs ~$0.05–0.20 per full run** (~10–30 new signals needing LLM, translation via DeepL). Fine for weekly runs. Expensive when run 50× during debugging.
7. **enriched_summary < 100% is EXPECTED** — the enricher intentionally clears `enriched_summary` when it's title-redundant (two checks: 70% overlap pre-merge, 85% overlap at finalization). These signals show the title in the UI, which is correct. They are still marked as processed in progress — re-running the enricher does NOT re-process them. Typical coverage: 40–60% of signals have a distinct enriched_summary; the rest use the title.

### Cost breakdown (with DeepL in place)
- Translation: ~45K chars/run via DeepL ≈ **free** (within 500K/month quota)
- LLM enrichment: 10–30 new signals × ~500 tokens ≈ $0.05–0.15/run
- Safety-net translation pass in enricher: ~0 fields (already translated by step 3)
- Total: **~$0.05–0.20/run** (vs ~$0.30–0.50 before DeepL re-integration)

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
- Portfolio company M&A (the class of bugs fixed Feb 2026): all 8 BeBeez parenthetical patterns, bolt-on/add-on, hyphenated-backed, Italian variants
- Deal vs exit disambiguation: evaluating/exploring a sale, completed sale, seller-side language
- Fundraise vs deal: final close, company rounds, ordinal investments
- People move: rescue from other, demotion of false positives
- Debt financing vs deal: bonds, credit facilities, restructuring agreements
- Universal demotions: press reviews, events, editorials, opinion
- Other → type rescue: over-demoted signals with clear type indicators
- **Section 8 (`TestFeb2026AuditRegressions`)**: exact signal IDs from the Feb 2026 audit — every signal fix committed during that audit has a corresponding regression test

**When changing classification logic**: at least one test in this suite must break or a new test must be added. If nothing breaks, the change may be silently wrong.
