# Web App — Claude Code Instructions

## AI Model Policy
**DO NOT use ChatGPT 4o for any task.** That model hallucinates too frequently. Use `gpt-5-mini` or better for all OpenAI API calls.

## Architecture
Next.js 14 App Router. All data from JSON files on disk — no database, no API layer for data reads. Components use inline styles (no Tailwind). Charts use Recharts.

## The Cache Problem — Read This First

`data.ts` has module-level `let cached*` variables. They are populated on first access and **never cleared** until the Node.js process exits. There is no TTL, no file-watcher, no invalidation API.

**Consequence**: after any worker run that updates `data/derived/*.json`, you MUST restart `pnpm dev` to see changes in the browser. This is the single most common source of confusion.

### All Caches
```
cachedDb              → db.json (+ linkedin URLs merged at load time)
cachedPemDeals        → pem_deals.json
cachedFilteredSignals → detected_signals_filtered.json
cachedPortfolios      → portfolio_items.json (includes fund_source_urls)
cachedLinkedInUrls    → linkedin/fund_linkedin_urls.json
cachedTeamAnalytics   → fund_people_stats.json
cachedCompanyProfiles → company_profiles.json (canonical sector/HQ/description/website per company)
```

### What NOT To Do
- Do NOT add a new `let cached*` variable without understanding that it persists forever
- Do NOT bypass `data.ts` to read JSON directly in pages/components — all reads must go through loaders
- Do NOT assume clearing one cache invalidates related data (e.g., clearing `cachedFilteredSignals` won't affect the portfolio merge which also reads signals)

## Critical File: src/lib/data.ts

This file is the central data layer. Every page reads data through it. It contains:
- Cache variables for each data source
- Loader functions following an identical pattern (check cache → read file → parse JSON → store in cache)
- Portfolio merge logic (website + PEM merge in `getPortfolioForFund`)
- Portfolio entry validation (`isValidPortfolioEntry`)
- Company name normalization for deduplication

### Path Resolution
`getRepoRoot()` tries 3 candidates based on `process.cwd()`:
1. `../../` (from `apps/web/`)
2. `../` (from `apps/`)
3. `.` (from repo root)

Falls back to `../../` if none match — **this fallback can be wrong** in non-standard environments. Never hardcode absolute paths; always go through `getRepoRoot()`.

### Error Handling — Inconsistent
- Some loaders log errors with `console.error` (loadDatabase, loadFilteredSignals, loadPortfolios)
- Some loaders silently return empty defaults (loadPortfolioSourceUrls)
- File-not-found vs parse-error are not distinguished
- Follow the existing pattern of whichever loader is closest to what you're adding

## Fund Visibility — Gemini-Confirmed Zero-Italy Funds

**Rule**: Funds confirmed by Gemini to have zero Italian assets must NOT appear on the website.

A fund is "confirmed zero-Italy" when **all** of these are true:
1. `completion_ready=True` in `gemini_fund_asset_audit.json` (audit ran fully)
2. `italian_portfolio_count=0` (no existing Italian entries)
3. `missing_assets=[]` (Gemini found nothing missing either)

**Current confirmed list**: `gemini_fund_asset_zero_italy_verified.json` → `verified_slugs[]`
As of 2026-02-27: `["canova-sgr"]`

**Implementation needed** (not yet done): Filter `getAllFunds()` to exclude slugs in `verified_slugs`. Load `gemini_fund_asset_zero_italy_verified.json` at startup (add to the cache list), join against `getAllFunds()`, and strip the matching slugs before returning. The fund page at `/funds/[slug]` should 404 for hidden funds. `generateStaticParams()` must also exclude them.

**Important**: only hide funds that are IN `verified_slugs`. Do NOT hide funds simply because they have 0 portfolio entries — those may not have been audited yet. The whitelist is the authoritative gate.

**How to add a fund to the whitelist**: after a passing audit (`completion_ready=True`, `missing_assets=[]`, `italian_portfolio_count=0`), add its slug to `gemini_fund_asset_zero_italy_verified.json` manually. Re-run the audit script if unsure — it reads this file and uses it in completion checks.

## Exported Functions (data.ts)

| Function | Returns | Source File(s) |
|----------|---------|----------------|
| `loadDatabase()` | Full DB with funds | `db.json` |
| `getAllFunds()` | `Fund[]` | via `loadDatabase()` |
| `getFundBySlug(slug)` | `Fund \| undefined` | via `loadDatabase()` |
| `getDealsForFund(slug)` | `Deal[]` | `pem_deals.json` |
| `getSignalsForFund(slug)` | `Signal[]` | `detected_signals_filtered.json` |
| `getPortfolioForFund(slug)` | `PortfolioCompany[]` | website + PEM merge (see below) |
| `getPortfolioGeoScope(slug)` | `string` | `portfolio_items.json` |
| `getAllPortfolioCompanyNames()` | `Record<string, string[]>` | `portfolio_items.json` |
| `getAllCompanies()` | `Company[]` | aggregated from all funds' `getPortfolioForFund()` |
| `getCompanyBySlug(slug)` | `Company \| undefined` | via `getAllCompanies()` |
| `getTeamAnalyticsForFund(slug)` | `TeamAnalytics \| null` | `fund_people_stats.json` |
| `isMegaFund(slug)` | `boolean` | `MEGA_FUNDS` set in `data.ts` |
| `getManualLinkedinProfileFundSlugs()` | `string[]` | `linkedin/manual_profiles.json` (+ alias normalization) |
| `isManualLinkedinProfileFund(slug)` | `boolean` | via `getManualLinkedinProfileFundSlugs()` |

### Company Page Data — `getAllCompanies()` aggregation

Company pages (`/companies/[slug]`) display a single `Company` object aggregated from all fund portfolio entries for that company. The `getAllCompanies()` function iterates every fund's portfolio and groups entries by `compactName(normalizeCompanyName(name))`.

**Merge behavior (first-fund-wins with gap-fill)**:
- First fund encountered sets the canonical sector/HQ/description/website
- Subsequent funds only contribute if the first had `null` — gap-fill only
- **No quality preference in the web layer** — it relies on `portfolio_items.json` already having canonical, consistent values before it runs

**Why this works now**: `signal_to_portfolio.py` runs a KB normalization pass on every pipeline execution that ensures all fund portfolio entries for the same company have the same sector/HQ/website (filling gaps and upgrading non-standard sectors). By the time `getAllCompanies()` runs, first-fund-wins is harmless because all funds agree.

**Before KB normalization**: company pages showed whatever the first db.json-ordered fund had — arbitrary, no quality preference. D-Orbit's company page sector was "Spacetech" or "Space Technology" depending on which fund appeared first in `getAllFunds()`.

**Remaining limitation**: HQ in the KB is selected by most-common vote (not Gemini-source-aware). If a wrong HQ from scraping appears in more funds than the Gemini-correct one, the web page will show the wrong one. Current workaround: manual fix in `portfolio_items.json` for the conflicting entries (they show up in the `signal_to_portfolio.py` conflict report). Improvement path: weight entries with `headquarters_source_url` set higher in the KB vote.

## LinkedIn People Analytics Source-of-Truth

- `MEGA_FUNDS` is only for excluding misleading dummy analytics for global funds with no real data.
- "Italy-only profiles" note coverage comes only from `data/derived/linkedin/manual_profiles.json`.
- Never infer manual-profile coverage from mega-fund membership.

## Page → Data Mapping

| Page Route | Data Functions | Source Files |
|------------|---------------|--------------|
| `/` | `getAllFunds()` | `db.json` |
| `/funds/[slug]` | `getFundBySlug()` | `db.json` |
| `/funds/[slug]` | `getPortfolioForFund()` | `portfolio_items.json` + `pem_deals.json` |
| `/funds/[slug]` | `getDealsForFund()` | `pem_deals.json` |
| `/funds/[slug]` | `getTeamAnalyticsForFund()` | `fund_people_stats.json` |
| `/funds/[slug]` | `getSignalsForFund()` | `detected_signals_filtered.json` ONLY |
| `/companies` | `getAllCompanies()` | aggregated from all `getPortfolioForFund()` |
| `/companies/[slug]` | `getCompanyBySlug()` | aggregated from all `getPortfolioForFund()` |
| `/companies/[slug]` | `getSignalsForCompany()` | `detected_signals_enriched.json` (company-matched) |
| `/signals` | `loadUnifiedSignals()` | enriched → filtered → raw (via `signals_unified.ts`) |
| `/subscribe` | Stripe checkout | — |
| `/login`, `/signup`, `/watchlists` | Redirect to `/subscribe` | — |

## Signal Dual-Loading — Important

Signals are loaded via **two different code paths** depending on the page:

Both paths share signal processing via **`signalProcessing.ts`** (defense-in-depth — Python `filter_signals.py` is the primary gate):
- `isGarbageSignal()` — filters nav text, stock photo descriptions, misattributed signals (KNOWN_FUND_NAMES check + SGR mention), Italy-relevance safety net (`italy_relevant === false` with no EU mention), truncated titles, event attendance
- `cleanSignalTitle()` — strips "Press release" prefix, date prefixes/suffixes, newspaper attribution suffixes, ALL CAPS→title case, curly quotes
- `cleanSignalText()` — strips read-time labels, newspaper-only text (e.g. "Il Sole 24 Ore"), fixes spacing, strips leading labels
- `fixSignalSpacing()` — digit-letter spacing, camelCase splitting, known name corrections (CDP VC artifacts: WSense, 3DNextech, etc. + IDeA, DeA Capital, B4 Investimenti, NeXt RE)
- `reclassifySignalType()` — event/conference demotion to `website_change`, event title demotion, VC fund portfolio company rounds→deal, financial results→other, research/publications→other, job posting detection, type corrections (fund_launch→deal, fundraise→deal/closed, deal→fund_launch, ordinal investment→deal, board→people_move, chiude la raccolta→fundraise_closed)
- `normalizeSignalText()` — lowercase + strip non-alphanumeric (for dedup)

**`/signals` page** uses `signals_unified.ts`:
- Tries files in priority: `detected_signals_enriched.json` → `detected_signals_filtered.json` → `detected_signals.json`
- Normalizes to `UnifiedSignal` (extends Signal with `fund_name`, `page_category`, `diff_summary`, `enriched_summary`, `signal_types`)
- `signal_types?: SignalType[]` carries all types detected in a signal (e.g. `["fundraise_closed", "exit_announced"]`); primary type is always first. Rendered as secondary badges in `SignalCard.tsx`.
- 4-check dedup (same loop pass for first 3, separate pass for semantic):
  1. **Composite key** `source_url::what_changed::published_at` — exact match
  2. **Content key** `normText::published_at` — same content, different URL
  3. **Cross-fund key** `source_url::normTitle` — same article published under multiple fund slugs; merges fund tags via `mergeRelatedFundTags()`. Uses title as fallback when `what_changed` is empty (prevents CDP newsroom signals from all collapsing to one)
  4. **Semantic dedup** (within same `fund_slug`, tiered thresholds): 40% overlap within 3 days; 50% within 7 days (both dates known); 60% when dates are unknown. Cross-language Italian↔English equivalences applied via `CROSS_LANG` map.
- **`DEDUP_STRUCTURAL_WORDS`** strips fund-name slug words + PE/VC structural terms + English stop-words (articles, prepositions, conjunctions) before overlap calculation. The English stop-words are critical: without them, ecosystem newsroom funds whose titles all start with the fund name (e.g. "CDP Venture Capital invests in X") share many function words after slug stripping and get falsely deduped. **Do NOT remove the stop-words.** (Fixed Feb 2026 — recovered 7 incorrectly collapsed CDP signals.)
- Does NOT cache — re-reads files on every call
- Shows AI-enriched summaries when available

**`/funds/[slug]` page** uses `data.ts`:
- Reads `detected_signals_filtered.json` ONLY — never sees enriched data
- Caches via `cachedFilteredSignals` (persists for server lifetime)
- Deduplicates using same composite key
- Shows raw `what_changed` text, never enriched summaries

**Result**: Both pages apply identical signal processing (garbage filter, title cleaning, reclassification). They still differ in source files (enriched vs filtered) and caching behavior.

## Signal-to-Fund Text Matching (signalFundTags.ts)

`signalFundTags.ts` matches signal text against fund names to determine which signals appear on each fund's page. `resolveSignalFundSlugs()` scans signal title/what_changed/enriched_summary against patterns built from all fund names.

### How `buildFundMentionEntries()` creates patterns

For each fund, three pattern types are generated:
1. **Full name**: e.g., `"permira associati"` — exact multi-word match
2. **Cleaned name**: strips legal suffixes (SGR, S.p.A., etc.) — e.g., `"permira associati"` → `"permira associati"` (no change if no suffix)
3. **First-word short brand**: for names where first word ≥6 chars and not in `GENERIC_SHORT_BRANDS` — e.g., `"permira"` from "Permira Associati", `"azimut"` from "Azimut Libera Impresa SGR". Only kept when the first word uniquely identifies exactly one fund (uniqueness filter).

### Cross-entity misattribution — the #1 risk

**BUG CLASS**: If a fund name's first word is a common noun that appears in other entity names, signals about those entities get wrongly attributed to the fund. Example: "Cherry Bay Capital" → first word "cherry" → matches "Cherry Bank" in signal text.

**Prevention** (two defenses):
1. **`GENERIC_SHORT_BRANDS` blocklist**: Common nouns (cherry, silver, golden, bridge, etc.) are blocked from becoming patterns regardless of name length.
2. **Uniqueness filter**: A short-word pattern is only kept if it maps to exactly one fund across all of db.json. If any other fund shares the same first word, the pattern is silently dropped.

Note: a previous ≤2-word count gate was removed (Feb 2026) — it blocked valid matches for 3+ word fund names (e.g., "Azimut Libera Impresa SGR"). The uniqueness filter already provides the necessary safety.

**When adding a fund**: If the fund name's first word could match other entities, add it to `GENERIC_SHORT_BRANDS`. After running the pipeline, verify no misattributed signals appear on the fund's page.

## Portfolio Merge Logic (getPortfolioForFund)

Merges from 2 sources:

1. **Website portfolio** (`portfolio_items.json`) — `data_source: 'fund_website'`
   - Companies default to `status: 'current'`
   - Source URLs stored in same file under `fund_source_urls` key
   - Includes both scraped entries AND manually added entries (same format, same file)

2. **PEM deals** (`pem_deals.json`) — `data_source: 'pem'`
   - If company name matches a website entry: **mutates the website entry in-place** to add PEM data (entry_date, sector, deal details)
   - If no match: added as new entry with `status: 'exited'`
   - `entry_date` is fabricated as `${source_year}-01-01` when only year is known

Signal-derived portfolio entries were removed (too fragile, #1 source of garbage). Deal signals remain visible in the Signals tab but no longer create portfolio entries.

**Watch out**: The in-place mutation pattern means the cached `websiteCompanies` array gets modified. This is safe because the cache is populated fresh per server start, but it would break if anyone added cache clearing without re-reading the portfolio file.

Result sorted: current → partial → exited → unknown, then by date, then alphabetically.

### PEM Merge — 4 Matching Strategies (in order)

When a PEM deal tries to match a website/manual portfolio entry, these strategies are tried in sequence. If **none** match, the PEM deal appears as a **separate exited entry** — this is the #1 source of duplicate entries on fund pages.

| # | Strategy | Example Match | Code |
|---|----------|---------------|------|
| 1 | **Exact normalized** | "CEME" ↔ "CEME" | `normalizeCompanyName(a) === normalizeCompanyName(b)` |
| 2 | **Compact** (no spaces) | "SF Filter" ↔ "SFFilter" | `compactName(norm_a) === compactName(norm_b)` |
| 3 | **Group-stripped** | "Nactarome Group" ↔ "Nactarome" | Strip "group" from normalized, compare |
| 4 | **Substring** (≥5 chars) | "Frigoveneta" ↔ "Frigoveneta Service" | Shorter appears at word boundary in longer |

`normalizeCompanyName()` pipeline: lowercase → strip parenthetical `(...)` → strip trailing "logo" → strip legal suffixes (SPA/SRL/SAS/SNC/SS) → strip trailing "Group" → strip trailing "Technologies" → non-alphanumeric → spaces → collapse → trim.

**Substring matching rules** (Strategy 4):
- Both names must be ≥5 chars after normalization
- The shorter name must appear in the longer name
- Match must start at a word boundary (start of string or after space)
- Match must end at a word boundary (end of string or before space)
- Example: "aussafer" (8 chars) found inside "aussafer due" at position 0 → match
- Counter-example: "ace" inside "palace" → rejected (only 3 chars, below minimum)

### Portfolio Entry Validation Pipeline

Before a portfolio entry reaches the merge logic, it passes through two filters:

1. **`cleanPortfolioName()`** — fixes scrape artifacts:
   - Strips trailing "logo" (image alt text)
   - Strips promotional suffixes via pipes ("| Invested by...", "| SGR name")
   - Strips remaining pipes (keeps text before first `|`)
   - Strips trailing periods and underscores

2. **`isValidPortfolioEntry()`** — rejects garbage:
   - NAV_PATTERNS: rejects navigation text ("Back to top", "Read more", "Cookie policy", etc.)
   - Rejects names that match the fund's own name
   - Rejects entries under 2 characters
   - Rejects entries that look like URLs, file paths, or promotional text

### Manual Portfolio Entries

When a fund has no working website extractor (common for large international PE firms), add entries directly to `portfolio_items.json` under `fund_portfolios[slug]`. Format:

```json
{
  "name": "Company Name",
  "sector": "Sector / Sub-sector",
  "status": "current",
  "confidence": 0.9,
  "website": "https://...",
  "description": "Brief description.",
  "detail_page_url": null,
  "headquarters": "City, Italy",
  "investment_date": "YYYY-01-01"
}
```

**Key rules for manual entries:**
- Use names that will normalize to match PEM deal names (verify with `normalizeCompanyName()`)
- Set `confidence: 0.9` or higher (these are verified from public sources)
- Set `status: "current"` for active investments, `"exited"` for completed
- Source from fund websites, press releases, AIFI data — never guess
- Worker runs will NOT overwrite manually added entries for funds that have no extractor (the worker only writes entries it extracts; missing funds keep their existing data)
- If the fund DOES have an extractor, manual entries will be overwritten on next `pnpm worker:monitor` run — in that case, fix the extractor instead

## Components

### `src/app/components/`
- `FundsTable.tsx` — home page table with search, filter, sort

### `src/components/`
- `PortfolioSection.tsx` — portfolio tab container
- `PortfolioTable.tsx` — portfolio company table
- `PortfolioInsights.tsx` — portfolio analytics/charts
- `TeamAnalyticsCharts.tsx` — Recharts-based team visualization

### `src/app/signals/`
- `SignalsFeed.tsx` — signal cards with type/source filters

### `src/lib/`
- `fundFilters.ts` — single source for fund filter catalogs and HQ-country filter logic shared by `FundsTable.tsx` and `MapView.tsx`
- `fundRangeFilters.ts` — shared AUM/investment range-stop utilities used by table/map slider filters

## Auth & Subscriptions

**No user accounts.** All data is freely accessible. The only user-facing feature requiring payment is email signal digests via `/subscribe` (Stripe).

- `/login`, `/signup`, `/watchlists` — redirect to `/subscribe` (no accounts)
- Auth API routes (`api/auth/*`) return 503 on Vercel via `process.env.VERCEL` guard
- Watchlist API routes (`api/watchlists/*`) return 503 on write operations
- `auth.ts`, `watchlist.ts`, `subscribers.ts` — have `IS_READONLY` guard to skip filesystem writes on Vercel
- `src/app/api/contact/route.ts` — contact form (works on Vercel)
- `src/app/api/stripe/*` — Stripe checkout and webhook (requires `STRIPE_SECRET_KEY` env var)

## Map & Address Data

The map page (`/map`) renders fund locations via `MapView.tsx` → `LeafletMap.tsx`. All location data comes from `db.json` via `loadDatabase()` — the same cache as every other page.

### Filter Source-of-Truth

- Fund filter behavior must stay aligned between home table (`FundsTable.tsx`) and map (`MapView.tsx`).
- Both must use `src/lib/fundFilters.ts` for:
  - category/sector filter options
  - HQ country derivation
  - HQ country filter matching
- Both must use shared slider/range helpers for investment and AUM filter controls:
  - `src/lib/fundRangeFilters.ts`
  - `src/components/filters/DualRangeSlider.tsx`
- Do not use `fund.geographies` for UI filtering on these pages.
- "HQ Country" means legal/actual HQ location, derived in priority:
  1. HQ office country from `offices[]` (`is_hq`)
  2. first office with a country
  3. fallback inference from `hq_city` / `hq_region`

### Location Resolution Priority

`MapView.tsx` resolves coordinates for each fund in this order:

1. **`offices[]`** array — prefers Italian office → HQ → any office with lat/lng
2. **`hq_lat` / `hq_lng`** fields — direct coordinate fields on the fund object
3. **`cityCoordinates.ts`** — hardcoded fallback for Italian cities, matched by `hq_city`

Authoritative coordinates come from Nominatim geocoding → `fund_coordinates.json` → merged into `db.json` via `merge-aifi-metrics.ts`. The `cityCoordinates.ts` fallback is static and only covers cities, not exact addresses.

### Key Files

| File | Role |
|------|------|
| `src/lib/fundFilters.ts` | Shared filter catalog + HQ-country derivation/matching |
| `src/lib/fundRangeFilters.ts` | Shared AUM/investment stop generation + formatting |
| `src/components/filters/DualRangeSlider.tsx` | Shared dual-thumb range slider UI |
| `src/app/map/MapView.tsx` | Filtering, coordinate resolution, data prep |
| `src/app/map/LeafletMap.tsx` | Leaflet rendering (client component) |
| `src/app/map/cityCoordinates.ts` | Static fallback coordinates for Italian cities |

### Do NOT

- Read `fund_coordinates.json` directly in web code — it's a geocoding cache for the merge step only
- Add a second location data source — `db.json` is the single source of truth
- Modify `cityCoordinates.ts` to add fund-specific coordinates — instead, run `pnpm worker:geocode && pnpm merge-aifi` to populate `db.json`

## Adding a New Data Type

1. Add TypeScript type in `packages/shared/src/types.ts`
2. Add loader function in `data.ts` following the existing pattern:
   - Module-level `let cached*: Type | null = null` variable
   - Load function: check cache → build path via `getRepoRoot()` → `existsSync` → `readFileSync` → `JSON.parse` → store in cache
   - Export query function(s) that call the loader
   - Add `console.error` on parse failure, return empty default
3. Add to the page component that needs it (server component, direct call)
4. Ensure the worker writes the corresponding JSON to `data/derived/`
5. Update the Page → Data Mapping table above
6. Manually verify the worker's JSON output matches your TypeScript type (no runtime validation exists)

## Fund Quality Scoring (`fundQuality.ts`)

Internal-only module for evaluating data completeness per fund. NOT displayed on the website — used via `pnpm audit:quality` to generate a ranked report identifying which funds need the most data improvement.

### Scored Sections (4 sections, weighted composite 0-100)

| Section | Weight | What it measures |
|---------|--------|------------------|
| Portfolio | 40% | Current companies, source diversity, sector/website/date coverage, PEM deals |
| Signals | 25% | Quantity, type diversity, quality_score, Italy relevance, freshness |
| AIFI | 20% | AUM, fund count, portfolio count, executives, investment range, contacts |
| Profile | 15% | Category, website, description, location, sector/strategy tags |

**Team is excluded** — `fund_people_stats.json` contains dummy/placeholder data. Re-enable when real LinkedIn data is available.

### Signal Quality Fields (undeclared in TS)

The signal scoring reads Python-computed fields not declared in the `Signal` TypeScript interface:
- `quality_score` (number, 55-100): structural quality from `noise_filter.py`
- `relevance_score` (number, 0.0-0.885): Italy relevance from `relevance.py`
- `italy_relevant` (boolean): threshold-based classification
- `relevance_reasons` (string[]): why it's relevant
- `extracted_entities` (object): entities found in signal text

These are accessed via `(signal as any).field_name` in `fundQuality.ts`.

### Cache

One module-level `cachedQualities` variable (same no-TTL pattern as `data.ts`). Restart server/script to see fresh results after data changes.

### Grade Scale

A (≥80), B (≥60), C (≥40), D (≥20), F (<20)
