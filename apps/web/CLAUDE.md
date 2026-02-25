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
| `getTeamAnalyticsForFund(slug)` | `TeamAnalytics \| null` | `fund_people_stats.json` |
| `isMegaFund(slug)` | `boolean` | `MEGA_FUNDS` set in `data.ts` |
| `getManualLinkedinProfileFundSlugs()` | `string[]` | `linkedin/manual_profiles.json` (+ alias normalization) |
| `isManualLinkedinProfileFund(slug)` | `boolean` | via `getManualLinkedinProfileFundSlugs()` |

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
- Normalizes to `UnifiedSignal` (extends Signal with `fund_name`, `page_category`, `diff_summary`, `enriched_summary`)
- 3-layer dedup: composite key (`source_url::what_changed::published_at`), cross-fund dedup (`source_url::normTitle`), semantic dedup (50% word overlap within same fund_slug, with cross-language Italian↔English term equivalence)
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
3. **First-word short brand**: ONLY for names with ≤2 words, where first word ≥6 chars and not in `GENERIC_SHORT_BRANDS` — e.g., `"permira"` from "Permira Associati"

### Cross-entity misattribution — the #1 risk

**BUG CLASS**: If a fund name's first word is a common noun that appears in other entity names, signals about those entities get wrongly attributed to the fund. Example: "Cherry Bay Capital" → first word "cherry" → matches "Cherry Bank" in signal text.

**Prevention** (two defenses):
1. **Word count gate**: First-word patterns are ONLY created for names with ≤2 words. 3+ word names (e.g., "Cherry Bay Capital") rely on full/cleaned patterns only.
2. **`GENERIC_SHORT_BRANDS` blocklist**: Common nouns (cherry, silver, golden, bridge, etc.) are blocked from becoming patterns even for 2-word names.

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
