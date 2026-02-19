# Fundradar — SOTA Scraping & Monitoring Guidelines (Spec for Implementation)

> **Primary objective:** capture high-signal, public updates from fund websites (and adjacent public sources) to power Fundradar signals and enrichment.  
> **Second objective:** minimize stored data (MB/GB) and avoid snapshot bloat while preserving auditability.

---

## 1) Goals, constraints, and definitions

### Goals (ordered)
1. **Signals quality**: detect meaningful changes (new news posts, portfolio updates, team changes, etc.) with low false positives.
2. **Coverage**: robustly support heterogeneous PE/VC/Infra/Debt/Holdings sites (different IA, languages, CMS, JS).
3. **Efficiency**: minimize bytes fetched and stored; avoid storing full HTML for “no-change” checks.
4. **Auditability**: keep enough evidence to explain *why* a signal fired.

### Constraints
- Prefer **HTTP + HTML parsing** (requests) and only use **headless** as a fallback when content is JS-rendered.
- Be resilient to: 404 patterns, redirects, bot blocks (403/Cloudflare), TLS/SNI issues, slow/timeout hosts.

### Key terms
- **Entity**: a fund / SGR / firm (and potentially strategy sub-sites).
- **Page type**: normalized semantic category (news list, news detail, portfolio list, team list, etc.).
- **Snapshot**: stored representation of a page for comparison/audit (not necessarily raw HTML).
- **Extraction**: structured JSON derived from the page.
- **Fingerprint**: hash of normalized content used for change detection.

---

## 2) What to scrape: page types, value, and data contracts

Scrape and monitor by **page type** (MECE) rather than by arbitrary URLs. Each page type has a **contract** (fields) and **signal rules**.

### 2.1 Highest priority (Signal-first)

#### A) News / Insights / Press (LIST + DETAIL)
**Why:** highest signal density; frequent updates; often includes dated items.

**Extract (LIST):**
- `items[]`: `{title, date, url, category?, teaser?}`
- `pagination?`: `{next_url?}`

**Extract (DETAIL):**
- `{title, date_published?, date_updated?, author?, tags?, body_text, outbound_links[], canonical_url}`
- `entities?`: people/companies extracted (optional phase)

**Signals**
- New item (new URL)
- Newer date (published/updated)
- Material text change (body fingerprint change)

#### B) Portfolio / Investments / Case Studies (LIST + DETAIL)
**Extract (LIST):**
- `companies[]`: `{company_name, url?, status?, sector?, geography?, tags?}`

**Extract (DETAIL)** (when present):
- `{company_name, status?, entry_date?, exit_date?, description, industries?, geography?, deal_type?, links[]}`

**Signals**
- New company added
- Status changes (e.g., “exited”)
- New case study / portfolio page published

#### C) Team / People (LIST + DETAIL)
**Extract (LIST):**
- `people[]`: `{name, role, url?, location?, practice?, linkedin_url?, email? (usually omit), image_url?}`

**Extract (DETAIL)** (when present):
- `{name, role, bio_text, linkedin_url?, other_links[]}`

**Signals**
- Person added/removed
- Role changes
- Material bio change

> **Note:** Team pages can be noisy if they include dynamic UI elements. Always fingerprint **normalized roster** rather than raw HTML.

### 2.2 Medium priority (Enrichment / classification)

#### D) Funds / Strategy / Approach
**Extract**
- `funds[]`: `{name, vintage?, strategy, stage, sector_focus, geography_focus, ticket_size?, aum_claim?, aum_date?}`
- `strategy_text`

**Signals**
- New fund listed
- Strategy text material change (optional)

#### E) Events / Webinars
Useful for forward-looking signals. Extract: `{title, date, url, topic, speakers?}`.

#### F) Careers
Hiring/job posting signals (valuable). Extract: job title + location + date.
Classify as `job_posting` (not `website_change`) when the content is an actual open role.

### 2.3 Low priority (capture once; rarely monitor)
- About / Contact / Locations / ESG policy pages

---

## 3) URL discovery & classification (avoid 404 spam)

### 3.1 Discovery order (fastest → slowest)
1. **Sitemaps**: `/sitemap.xml`, `sitemap_index.xml`, CMS-specific sitemap endpoints  
2. **RSS/Atom** (especially for News): look for `<link rel="alternate" type="application/rss+xml">`
3. **Homepage nav+footer crawl** (depth=1) and classify discovered links
4. **Targeted heuristics**: if needed, search site for keywords (news/press/team/portfolio) via internal search endpoints only if available

### 3.2 Maintain an allowlist per entity
Store `monitor_urls.json` as **per entity** allowlist with explicit page types, e.g.:

```json
{
  "entity_id": "wise_sgr",
  "display_name": "Wise SGR",
  "domains": ["wisesgr.com"],
  "urls": [
    {"type": "home", "url": "https://www.wisesgr.com/"},
    {"type": "news_list", "url": "https://www.wisesgr.com/news/"},
    {"type": "team_list", "url": "https://www.wisesgr.com/team/"}
  ]
}
```

### 3.3 URL hygiene
- Normalize hostnames: try both `https://domain` and `https://www.domain` if one fails.
- Respect canonical URLs; de-duplicate by canonical.
- Strip tracking params; keep stable query params only when required.

### 3.4 Bot-Blocked Domains (Extractor-Level Routing)
- If top-level pages are blocked (`403`, WAF challenge), do not change the global pipeline first.
- Route that fund's extractor `URLS` to known deeper endpoints (press archive, newsroom, portfolio detail) or public JSON API endpoints.
- Add per-extractor fallback parsing for:
  - detail pages (`h1`, `time`, canonical URL),
  - API payloads (JSON),
  - mixed list/detail layouts.
- If the official domain is fully blocked, use scoped RSS/Atom feed URLs as extractor `news` endpoints (the monitor generic news parser supports XML feed items).
- Keep this fund-by-fund and additive: monitor/pipeline behavior stays unchanged.

---

## 4) Fetching strategy (minimize bytes, maximize reliability)

### 4.1 Prefer conditional requests
Use HTTP caching headers where available:
- Send `If-None-Match` with stored `ETag`
- Send `If-Modified-Since` with stored `Last-Modified`
- On `304 Not Modified`: do **not** store a new snapshot; only store a lightweight “check record”.

### 4.2 Content fetching rules
- Fetch **HTML only** (block images/fonts/video) unless explicitly needed.
- Set timeouts + retries with backoff.
- Respect robots.txt where applicable (at minimum, don’t hammer sites).
- Rate limit per domain; randomize small jitter.

### 4.3 Headless fallback
Use headless only if:
- HTML body is empty/placeholder and content is clearly JS-rendered
- Required fields (title/date/list items) are absent in server HTML

When using headless:
- Extract DOM and immediately run the same normalization/extraction pipeline.
- Still store only structured outputs unless a meaningful change occurs.

---

## 5) Normalize → fingerprint → compare (reduce false positives)

### 5.1 Normalization (strip noise)
Before fingerprinting, remove:
- nav/footer/sidebars, cookie banners, consent modals
- scripts/styles, tracking pixels, share widgets
- timestamps like “Last updated at 12:03” if not part of article metadata
- dynamic counters (views/likes), rotating “related content”

Canonicalize:
- whitespace, punctuation spacing
- URL normalization
- locale date normalization (convert to ISO `YYYY-MM-DD` when possible)

### 5.2 Fingerprints (recommended)
Store multiple hashes per page:
- `raw_hash` (optional; for debugging)
- `content_hash` = hash(normalized main content text)
- `structure_hash` = hash(structured extraction JSON, sorted keys)
- `list_hash` = hash(list of item URLs + dates) for list pages

**Signal decisions** should be based on:
- list pages → `list_hash` / extracted items diff
- detail pages → `structure_hash` + (optional) `content_hash`

---

## 6) Extraction approach (SOTA tiered extractor)

Extraction priority order:
1. **Structured data**: JSON-LD (`schema.org`), OpenGraph, meta tags
2. **List card patterns** (for list pages): title/date/url blocks
3. **Article/Detail parsing**: main content region, heading, date nodes
4. **Selectors registry** per domain only when heuristics fail (minimal bespoke code)

Confidence scoring (store in extraction JSON):
- `confidence`: `high|medium|low`
- `issues[]`: e.g., `missing_date`, `multiple_date_candidates`, `empty_body`

If confidence drops from high→low for a page that previously worked, store raw HTML for debugging automatically.

---

## 7) Storage model & retention (cut MB/GB)

### 7.1 What to store per check (default minimal)
Always store:
- `metadata.json`: status code, fetch timestamp, content-type, canonical URL, redirects, etag/last-modified, timings
- `extracted.json`: structured fields per page type + confidence
- fingerprints: `content_hash`, `structure_hash`, `list_hash` (as applicable)

Store `normalized.txt` only when helpful (cheap; optional).

### 7.2 Store raw HTML only when needed
Store compressed raw HTML **only if**:
- first time seen (baseline)
- meaningful change detected (fingerprint changed materially)
- extraction confidence drops
- debugging mode enabled for that domain/entity

### 7.3 Deduplication
Use content-addressed storage:
- store blobs under `/blobs/<hash>.html.zst` (or `.gz`)
- each snapshot references the blob hash
- if two snapshots have same blob hash, no extra storage

### 7.4 Retention policy (by page type)
- News detail: keep last **N=10** changed versions
- Portfolio/team: keep last **N=5** changed versions
- Low-priority pages: keep **N=2** changed versions
- Keep all **check records** (tiny) for audit: “we checked daily; no change”.

---

## 8) Signal generation rules (structured diff, not HTML diff)

Signals should be generated from **structured diffs**:
- News list: new URLs / newer dates / removed URLs (optional)
- Team list: set diff on people keys `(name, role)`; role change detection
- Portfolio list: set diff on `(company_name)`; status change detection

Signal payload schema (suggested):
- `signal_id`
- `entity_id`
- `timestamp`
- `page_type`
- `signal_type` (new_news, new_portfolio_company, team_change, etc.)
- `summary`
- `evidence`: `{url, changed_fields, diff_snippet?, old_hash, new_hash}`

**Avoid signals** triggered only by:
- navigation changes, cookie banners, counters, layout reordering without content change

---

## 9) Scheduling (adaptive, efficient)

Default cadence:
- News: daily
- Portfolio: weekly
- Team: weekly (or biweekly)
- Strategy/About: monthly or on-demand

Adaptive cadence:
- If a page never changes for 60 days → slow down (e.g., monthly)
- If a page changes frequently → speed up within limits

---

## 10) Resilience & anti-bot handling

### 10.1 Common failures and handling
- `404` on assumed endpoints (e.g., `/news`) → mark URL invalid; trigger discovery refresh for that domain.
- `403/429` → backoff; mark “blocked”; attempt alternate endpoints (RSS, sitemap).
- TLS hostname mismatch / cert issues → try non-www / correct host; do **not** disable TLS verification globally.
- Cloudflare `526` / WAF → fallback sources (RSS, press releases, socials) + lower frequency.

### 10.2 Per-domain strategy registry
Maintain `domain_policies.json`:
- `rate_limit`
- `requires_headless`
- `blocked_paths`
- `preferred_feeds`
- `known_sitemap_urls`

---

## 11) Metrics & monitoring (quality control, no cut corners)
Track:
- Coverage: % entities with working news/team/portfolio URLs
- Error rates by domain (404/403/timeouts)
- Extraction confidence distribution
- Storage: bytes stored per day; % checks that store raw HTML
- Signal precision: % signals confirmed meaningful (manual sampling)

Add a nightly report JSON (and optional markdown) in `data/derived/monitor_reports/`.

---

## 12) Implementation plan for Fundradar (incremental)

### Phase 1 — Make monitoring storage-efficient (highest ROI)
- Add caching headers support (ETag/Last-Modified) and store check records on 304.
- Implement normalization + fingerprints.
- Store structured extraction JSON per page.
- Store raw HTML only on first seen / meaningful change / low confidence.

**Acceptance criteria**
- Re-running monitor on same URLs yields near-zero new stored blobs when pages unchanged.
- Storage/day decreases substantially vs current snapshots.

### Phase 2 — Improve URL quality and reduce 404 spam
- Add discovery step (sitemap/RSS/nav crawl) per domain.
- Update `monitor_urls.json` generation to prefer discovered URLs vs guessed `/news`.
- Add “URL stale” state + auto-refresh discovery.

### Phase 3 — Stronger extraction and structured diffs
- Implement page-type specific extractors with confidence scoring.
- Implement signal generation from structured diffs.

### Phase 4 — Anti-bot + adaptive scheduling
- Domain policy registry + adaptive cadence.

---

## 13) Non-goals (for now)
- Full web crawling beyond page types above
- Paywalled content extraction
- Aggressive bypass of anti-bot systems
- Personal data enrichment beyond public professional info

---

## 14) Notes aligned to current repo behavior (observed)
- Many sites return 404 for `/news` `/portfolio` `/team`; do not assume these endpoints.
- Several hosts fail DNS / TLS mismatch; add hostname normalization and domain policy handling.
- Current “Stored snapshot … First snapshot” suggests storing full HTML every time; Phase 1 is designed to fix this.

---

## 15) Quick checklist (Claude Code implementation)
- [ ] Add `FetchMetadata` model: `etag`, `last_modified`, `status_code`, `final_url`, `fetched_at`, `timings`
- [ ] Add `normalize_html_to_main_text()` and `fingerprint_*()` utilities
- [ ] Add per-page `extracted.json` schemas + confidence
- [ ] Implement “store blob only when needed” + content-addressed dedup
- [ ] Implement structured diff for news/team/portfolio
- [ ] Add domain policy overrides
- [ ] Add daily report generation + storage metrics
