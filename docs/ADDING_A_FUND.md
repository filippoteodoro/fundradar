# Adding a New Fund to Fundradar — Complete Guide

This is the definitive, step-by-step guide to correctly adding a new fund to Fundradar, from initial research through to production deployment.

> **Canonical references**: For pipeline internals see `apps/worker/CLAUDE.md`. For web app caching and data loading see `apps/web/CLAUDE.md`. For project-wide rules see root `CLAUDE.md`. This guide focuses on the **workflow** of adding a fund and references those docs for deep dives.

---

## Table of Contents

1. [Prerequisites & Eligibility](#1-prerequisites--eligibility)
2. [Research the Fund](#2-research-the-fund)
3. [Add the Fund Entry to db.json](#3-add-the-fund-entry-to-dbjson)
   - [3.5 Register variant names in fund_aliases.json](#35--register-variant-names-in-fund_aliasesjson)
   - [3.6 Clear gap detector state](#36--clear-gap-detector-state-after-adding-a-fund)
4. [Build the Custom Extractor](#4-build-the-custom-extractor)
5. [Test the Extractor](#5-test-the-extractor)
6. [Run the Pipeline](#6-run-the-pipeline)
7. [Enrich Portfolio Data with Gemini](#7-enrich-portfolio-data-with-gemini)
8. [Generate Fund Description (Optional)](#8-generate-fund-description-optional)
9. [Audit Portfolio Assets with Gemini](#9-audit-portfolio-assets-with-gemini)
10. [Enrich Fund Metadata with Gemini](#10-enrich-fund-metadata-with-gemini)
11. [Enrich Signals with OpenAI](#11-enrich-signals-with-openai)
12. [AIFI Data Merge (Optional)](#12-aifi-data-merge-optional)
13. [Geocoding & Map (Optional)](#13-geocoding--map-optional)
14. [Verify Frontend Display](#14-verify-frontend-display)
15. [Sitemap & llms.txt (Automatic)](#15-sitemap--llmstxt-automatic)
16. [Assets & OG Images (Automatic)](#16-assets--og-images-automatic)
17. [Commit & Deploy](#17-commit--deploy)
18. [Verify Data Quality (MANDATORY)](#18-verify-data-quality-mandatory) — Automated checks + Gemini enrichment + asset audit + verification loop
19. [Post-Deployment Checklist](#19-post-deployment-checklist)
20. [Reference: db.json Field Catalog](#reference-dbjson-field-catalog)
21. [Reference: Extractor Template & Patterns](#reference-extractor-template--patterns)
22. [Reference: Common Pitfalls](#reference-common-pitfalls)

---

## 1. Prerequisites & Eligibility

### What belongs in Fundradar

Only **Private Equity, Venture Capital, and Growth Equity** funds with Italian operations belong in `db.json`.

### What does NOT belong

| Entity Type | Example | Why Not |
|---|---|---|
| Asset managers | Generali Investments, Amundi, BlackRock | Diversified portfolios, not PE/VC |
| Banks | Banca Generali, BancoBPM Invest | Deposit-taking institutions |
| Regional agencies | Trentino Sviluppo, Lazio Innova, Finlombarda | Public development agencies |
| Credit-only vehicles | Clessidra Capital Credit SGR | Private debt, not equity |

**Quick test**: Check the entity's website. If it says "asset management", "wealth management", "banking", or "credit" — it's not PE/VC. If it says "private equity", "venture capital", "growth equity", "buyout", or "infrastructure investments" — it belongs.

Excluded entities are blocked via `invalid_slugs` in `data/derived/fund_aliases.json` and `EXCLUDED_SLUGS` in `scripts/merge-aifi-metrics.ts`.

### Before you start

1. **Check if the fund already exists** in `db.json`:
   ```bash
   python3 -c "import json; [print(f['slug'], f['name']) for f in json.load(open('data/db.json'))['funds'] if 'SEARCH_TERM' in f.get('name','').lower()]"
   ```
2. **Check `fund_aliases.json`** for variant names that might canonicalize to an existing fund. Structure:
   ```json
   {
     "aliases": { "legacy-slug": "canonical-slug" },
     "invalid_slugs": ["bank-slug", "asset-manager-slug"],
     "reverse_lookup": { "canonical-slug": ["legacy-slug"] }
   }
   ```
   - If a variant slug maps to an existing fund, use the canonical slug — don't create a new entry.
   - If the fund was previously added under a different legal name (common after AIFI scrapes), add an alias mapping to `fund_aliases.json` instead of creating a duplicate.
3. **Check `invalid_slugs`** in `data/derived/fund_aliases.json` — the fund might be explicitly blocked.

---

## 2. Research the Fund

Before writing any code, gather this information:

### 2.1 — Visit the fund's website

Open the fund's official website and locate:

| Page | What to look for | Example paths |
|---|---|---|
| **Portfolio page** | List of current/past investments | `/portfolio/`, `/investimenti/`, `/our-companies/`, `/portafoglio/` |
| **Team page** | People, leadership | `/team/`, `/chi-siamo/`, `/about/`, `/persone/` |
| **News/Press page** | Press releases, news | `/news/`, `/newsroom/`, `/media/`, `/press/` |

**Record the exact URL paths.** Do NOT guess — open each page in a browser and confirm it loads with relevant content.

### 2.2 — Check AIFI

If the fund is an AIFI member, check `data/AIFI/all.csv` for authoritative data:
```bash
grep -i "FUND_NAME" data/AIFI/all.csv
```

AIFI provides: official website URL, AUM, contact info, investment ranges, geographies. **AIFI website URLs are authoritative** — verify your `website` field in `db.json` matches.

> **AIFI name cleaning**: AIFI registers members by legal entity name (e.g., "Example Partners SGR S.p.A. - Italian Branch"), not brand name. The `clean_fund_name()` function in `aifi_scraper.py` automatically strips branch suffixes, parenthesized legal info, and trailing "Italy"/"Italia". If the cleaned name still doesn't match the fund's actual brand name (check their homepage), add an override to `AIFI_NAME_OVERRIDES` dict in `aifi_scraper.py`.

### 2.3 — Determine the fund's scope

| Scope | Meaning | Example |
|---|---|---|
| `italy_focused` | HQ in Italy + invests primarily in Italy | 21 Invest, Clessidra |
| `europe_wide` | European fund with Italian operations | Ardian, Permira |
| `mixed_or_global` | Global mega-fund with some Italian deals | Blackstone, KKR |

This affects how the signal filter's geo gate treats the fund's signals. See `apps/worker/CLAUDE.md` for the full 3-tier gate logic.

### 2.4 — Check if the website blocks scraping

Some fund websites block headless browsers entirely or require JavaScript rendering. Signs:
- **403 Forbidden** when fetched programmatically
- **Blank page** that only renders with JavaScript (React/Vue/Angular/Next.js SPAs)
- **Cloudflare/Akamai challenge pages**

The system handles this via `data/derived/domain_policies.json`, which tracks per-domain settings:
- `requires_headless: true` — site needs Playwright (auto-detected for JS-heavy sites)
- Custom timeouts, rate limits, SSL settings

Known problem domains (as of last update):
- **Bridgepoint** — requires headless browser (AEM/Adobe Experience Manager site, JavaScript-rendered). The extractor works but needs `requires_headless: true` in domain policies.
- **EnTrust Global** — blocks ALL automated access (ShieldPRO anti-bot). Manual portfolio entries are the only option. The extractor exists but has all URLS set to `None`.

Check `apps/worker/CLAUDE.md` and `data/derived/domain_policies.json` for the current list of domains requiring special handling.

---

## 3. Add the Fund Entry to db.json

### 3.1 — Generate the slug

Rules for slug generation:
- **Lowercase** everything
- **Hyphens** for spaces: `"Bain Capital"` → `bain-capital`
- **Strip legal suffixes**: SGR, S.p.A., S.r.l., etc.
- **No special characters**: strip accents, apostrophes
- **Must be unique** in db.json

### 3.2 — Add the entry

Open `data/db.json` and add a new object to the `funds` array. Here's a minimal entry:

```json
{
  "id": "example-fund",
  "slug": "example-fund",
  "name": "Example Fund",
  "category": "pe",
  "hq_city": "Milan",
  "hq_region": "Italy",
  "website": "https://www.example-fund.com",
  "strategy_tags": ["Buy-Out"],
  "sector_tags": ["Technology", "Healthcare"],
  "description": "Example Fund is a private equity firm focused on mid-market buyouts in Italy.",
  "geographies": ["Italy"],
  "aum_eur": null,
  "created_at": "2026-02-24T00:00:00.000Z",
  "updated_at": "2026-02-24T00:00:00.000Z"
}
```

### 3.3 — Category values

The full list of valid categories is the `FundCategory` type in `packages/shared/src/types.ts`. The most common ones for new funds:

| Category | Slug | When to use |
|---|---|---|
| Private Equity | `pe` | Traditional buyout/control |
| Venture Capital | `vc` | Early/growth stage startups |
| Growth Equity | `growth` | Growth capital without full control |
| Infrastructure | `infra` | Infrastructure and real assets |
| Private Debt | `debt` | Credit, mezzanine, direct lending |
| Multi-Strategy | `multi_strategy` | Multiple strategies across asset classes |
| Holdings | `holdings` | Holding companies |
| Fund of Funds | `fund_of_funds` | Invests in other PE/VC funds |
| Sovereign | `sovereign` | State-backed investment vehicles |
| Real Estate | `real_estate` | Real estate investment |

> **Source of truth**: Always check `FundCategory` in `packages/shared/src/types.ts` for the authoritative list — categories may have been added since this doc was last updated.

### 3.4 — Optional flags

| Flag | Type | When to set |
|---|---|---|
| `is_ecosystem_newsroom` | `boolean` | Fund's news page covers the ENTIRE market, not just its own activity. Rare — search `db.json` for `is_ecosystem_newsroom` to see current list. |
| `aum_eur` | `number` | AUM in EUR (**NOT `aum`** — the field name is `aum_eur`) |
| `investment_min_eur` | `number` | Minimum ticket size (**NOT `investment_min`**) |
| `investment_max_eur` | `number` | Maximum ticket size (**NOT `investment_max`**) |

See the [full field catalog](#reference-dbjson-field-catalog) at the end of this document.

### 3.5 — Register variant names in fund_aliases.json

If the fund is known by short-form brands, old legal names, or hyphenation variants, register them in `data/derived/fund_aliases.json` so the pipeline resolves them to the canonical slug:

```json
{
  "aliases": {
    "indaco":                    "indaco-venture-partners-sgr",
    "indaco-sgr":                "indaco-venture-partners-sgr",
    "indaco-venture-partners":   "indaco-venture-partners-sgr"
  },
  "reverse_lookup": {
    "indaco-venture-partners-sgr": ["indaco", "indaco-sgr", "indaco-venture-partners"]
  }
}
```

Keep `aliases` and `reverse_lookup` in sync manually — the file has no auto-generation.

**When to add aliases:**
- Short-form brand: `"Indaco"` → full canonical slug
- Pre-rebrand name: `"old-legal-name-sgr"` → current canonical slug
- Legal entity variant: `"fund-name-spa"` → `"fund-name"`

**When NOT to add aliases — use `invalid_slugs` instead:**
- Non-PE/VC entities (asset managers, banks, regional agencies)
- Generic words that appear in many signal bodies (`investimento`, `partners`, `capital`)

### 3.6 — Clear gap detector state after adding a fund

`data/derived/unknown_fund_gaps.json` is a dedup state file that prevents the Telegram gap-alert from firing twice for the same unrecognised fund name within a 30-day window. When a fund name appeared in signals **before** you added it to `db.json`, old alerts are suppressed by that state — new pipeline runs won't re-fire them even though the gaps are now resolved.

After adding the fund and its aliases, check the state:

```bash
python3 -c "
import json
gaps = json.load(open('data/derived/unknown_fund_gaps.json')).get('gaps', [])
print(f'{len(gaps)} dedup entries')
for g in gaps[:10]:
    print(f'  {g[\"fund_name\"]:40s}  {g[\"signal_id\"]}')
"
```

If any entries correspond to the fund you just added (or its aliases), **clear the file** so the gap detector treats those mentions as resolved and won't fire stale alerts:

```bash
echo '{"gaps": []}' > data/derived/unknown_fund_gaps.json
```

This is safe — the file is recreated on the next pipeline run. Only clear it when all listed gaps are genuinely resolved (i.e. the fund is now in `db.json` or `invalid_slugs`).

---

## 4. Build the Custom Extractor

### 4.1 — Create the file

```bash
cp apps/worker/fundradar_worker/strategies/extractors/_template.py \
   apps/worker/fundradar_worker/strategies/extractors/{fund_slug}.py
```

**Naming**: Use the fund slug with underscores instead of hyphens (Python module naming). Example: `bain_capital.py` for slug `bain-capital`.

> **Note**: The filename doesn't affect URL routing — only the `DOMAIN` constant inside the file matters. But convention is to match the slug. Some historical exceptions exist (e.g., `ottoapiu.py` → slug `8a-investimenti-sgr`).

### 4.2 — Set the three required exports

Every extractor **must** export exactly three things:

#### 1. `DOMAIN` — The exact domain

```python
DOMAIN = "www.example-fund.com"  # Must match db.json website domain exactly
```

**This is how the system routes fetched HTML to your extractor.** If `DOMAIN` doesn't exactly match the domain in `db.json`'s `website` field, the extractor will never be called. This is the #1 cause of "my extractor doesn't run" issues.

#### 2. `URLS` — The page paths to fetch

```python
URLS = {
    "portfolio": "/portfolio/",           # Required if portfolio exists
    "team": "/team/",                     # Optional — set to None if no team page
    "news": "/news/",                     # Optional — set to None if no news page
}
```

**CRITICAL RULES for URLS:**
- **Every path MUST be verified against the live website** — open it in a browser, confirm it returns 200 and has relevant content.
- **NEVER use generic template paths** like `/investments`, `/management` — these are placeholders that rarely exist on real websites.
- **Single-page sites**: Use `"/"` only when the homepage contains a real, structured portfolio/team list.
- **Never use `"/"` as a placeholder** just to satisfy checks. If no reliable public portfolio index exists, set `"portfolio": None` and keep portfolio data manual/PEM-derived. Placeholder homepages cause persistent garbage companies/signals.
- **Multiple pages**: Use a list — for example, when current and exited portfolios are on separate pages:
  ```python
  "portfolio": ["/current-investments/", "/past-investments/"]
  ```
  The monitor fetches each URL separately and calls `extract_portfolio()` on each. Your function receives one page at a time and returns companies from that page. The monitor merges results from all pages.
- **WordPress REST API**: Can use JSON API endpoints:
  ```python
  "news": "/wp-json/wp/v2/posts?per_page=20&_fields=id,title,date,link,excerpt"
  ```
  Your `extract_news()` function should try `json.loads(html)` first, with HTML parsing as fallback. See `abenex.py` for a production example.
- **Set to `None`** for page types that don't exist on this fund's website.

> **Legacy note**: `data/monitor-urls.md` is a legacy file with base domain URLs only. Do NOT add entries there — URLs are auto-discovered from extractor `URLS` dicts.

#### 3. `EXTRACTORS` — The extraction functions

```python
EXTRACTORS = {
    "portfolio": extract_portfolio,   # Required if URLS has portfolio
    "team": extract_team,             # Optional
    "news": extract_news,             # Optional
}
```

Only include functions you actually implemented. **Never include a function that doesn't exist.**

#### Optional: `ALWAYS_EXTRACT` flag

```python
ALWAYS_EXTRACT = True  # Bypass content hash check — always run extraction
```

Set this when the site fetches data from an API (e.g., WordPress REST API, JSON endpoints) where the HTML shell stays the same but the data changes. Without this flag, the monitor's content hash optimization sees "same HTML" and skips extraction even when API data has changed. See `merito_sgr.py` for an example.

### 4.3 — Implement `extract_portfolio()`

This is the most important function. It receives the raw HTML of the portfolio page and must return a list of company dicts.

```python
def extract_portfolio(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen_names = set()

    for item in soup.select("div.portfolio-item"):  # ← Adapt to actual HTML structure
        name_el = item.select_one("h3.company-name")  # ← Adapt
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Dedup
        name_lower = name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        # Sector
        sector = None
        sector_el = item.select_one(".sector")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        # Website
        website = None
        link_el = item.select_one("a[href]")
        if link_el and link_el.get("href", "").startswith("http"):
            website = link_el["href"]

        # Description
        description = None
        desc_el = item.select_one("p.description")
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",    # See status detection rules below
            "confidence": 0.90,
        })

    return companies
```

#### PEM merge matching — 4-strategy name resolution

When PEM deals try to match against website portfolio entries, these strategies run in order (see `apps/web/CLAUDE.md` "PEM Merge — 4 Matching Strategies" for full details):

1. **Exact normalized** — `normalizeCompanyName(a) === normalizeCompanyName(b)`
2. **Compact** — strip spaces: "SF Filter" ↔ "SFFilter"
3. **Group-stripped** — "Nactarome Group" ↔ "Nactarome"
4. **Substring** (≥5 chars, word boundary) — "Frigoveneta" ↔ "Frigoveneta Service"

**If none match**, the PEM deal appears as a separate exited entry — the #1 source of duplicates. Use names that will normalize to match PEM deal names.

#### Company name quality — what the frontend rejects

The web app's `isValidPortfolioEntry()` in `data.ts` silently rejects entries matching `NAV_PATTERNS` (navigation text like "Back to top", "Read more", "Cookie policy", fund's own name, names < 2 chars, URLs, file paths). `cleanPortfolioName()` also strips " logo" suffixes and pipe-delimited promotional text.

**Test your names**: If `extract_portfolio()` returns names that look like nav text, they'll silently disappear from the frontend with no error. Always visually inspect the first few results.

#### Status detection rules (CRITICAL)

| Page type | Default status | Example |
|---|---|---|
| Single portfolio page (`/portfolio/`) | `"current"` | Only shows active holdings |
| Dedicated exits page (`/realized/`, `/prior-investments/`) | `"exited"` | Only shows past investments |
| Multi-section page (tabs, filters) | Detect from structure | Use labeled fields, section headers, data attributes |
| Mixed/unclear page | `None` | Don't guess — incorrect status is worse than unknown |

**Safe detection patterns (priority order):**

1. **Data attributes** (best): `data-status="exited"`, `data-statut="cedute"`
2. **URL path**: The page path itself indicates status (`/current-portfolio/` vs `/prior-investments/`)
3. **Parent element class/ID**: `#invest-cedute`, `.realised-portfolio`
4. **Section headers**: Track h2/h3 headings like "Current" vs "Realised" in document order
5. **Labeled field values**: Check for a `Status:` label FIRST, then match the value (may be in Italian: "ceduto", "attivo")

**NEVER do this:**
```python
# BAD — matches "exit" anywhere in text, causes false positives
if "exit" in description.lower():
    status = "exited"
```

#### Confidence scores — when to use which value

| Confidence | When to use |
|---|---|
| 0.95 | Explicit data attributes, very clear structure, zero ambiguity |
| 0.90 | Clean selector-based extraction, one-to-one mapping |
| 0.85 | Default for well-structured sites |
| 0.80 | Some fuzzy matching or regex involved |
| 0.70 | Minimum recommended for extractors |
| < 0.3 | Filtered out by strategy orchestrator — never use this low |

### 4.4 — Implement `extract_team()` (optional)

```python
def extract_team(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    members = []

    for item in soup.select("div.team-member"):
        name_el = item.select_one("h3")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        title = None
        title_el = item.select_one(".title, .position")
        if title_el:
            title = title_el.get_text(strip=True)

        linkedin = None
        for link in item.select("a[href*='linkedin']"):
            linkedin = link.get("href")
            break

        photo_url = None
        img = item.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src")
            if src:
                photo_url = urljoin(base_url, src)

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": linkedin,
            "email": None,
            "photo_url": photo_url,
            "confidence": 0.85,
        })

    return members
```

### 4.5 — Implement `extract_news()` (optional)

```python
def extract_news(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    news = []

    for article in soup.select("article.post"):
        title_el = article.select_one("h2 a, h3 a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        url = None
        link = article.select_one("a[href]")
        if link:
            url = urljoin(base_url, link.get("href", ""))

        date = None
        date_el = article.select_one("time, .date, [datetime]")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        summary = None
        summary_el = article.select_one(".excerpt, .summary, p")
        if summary_el:
            summary = summary_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news
```

### 4.6 — How the extractor is auto-discovered

You do **not** need to register the extractor anywhere. The system auto-discovers it:

1. `extractors/__init__.py` uses `pkgutil.iter_modules()` to find all `.py` files in the extractors directory
2. Each module is imported. If it has `DOMAIN` and `EXTRACTORS` attributes, it's registered in `ALL_EXTRACTORS[domain]`
3. If it also has `URLS`, those are registered in `ALL_URLS[domain]`
4. `url_generator.py` reads `ALL_URLS` to build the list of URLs to fetch
5. `strategy_orchestrator.py` reads `ALL_EXTRACTORS` to route fetched HTML to the correct extractor

**When a site-specific extractor returns results, all generic strategies are skipped** for that domain. This prevents garbage from generic HTML parsing contaminating the results.

### 4.7 — When scraping is not possible: manual portfolio entries

If a fund's website blocks scraping entirely (Bridgepoint, EnTrust Global, or others), you can add portfolio entries directly to `portfolio_items.json`:

```json
{
  "fund_portfolios": {
    "fund-slug": [
      {
        "name": "Company Name",
        "sector": "Technology",
        "status": "current",
        "confidence": 0.9,
        "website": "https://company.com",
        "description": "Brief description.",
        "detail_page_url": null,
        "headquarters": "Milan, Italy",
        "investment_date": "2024-01-01"
      }
    ]
  }
}
```

**Rules for manual entries:**
- Source from fund websites, press releases, AIFI data — never guess
- Set `confidence: 0.9` or higher (verified from public sources)
- Use names that will normalize to match PEM deal names (check with `normalizeCompanyName()` in `data.ts`)
- If the fund DOES have a working extractor, manual entries will be **overwritten** on next monitor run — fix the extractor instead
- If the fund has NO extractor, manual entries persist across pipeline runs

See `apps/web/CLAUDE.md` "Manual Portfolio Entries" section for full details.

---

## 5. Test the Extractor

### 5.1 — Verify it loads

```bash
cd apps/worker
python -c "
from fundradar_worker.strategies.extractors.{fund_slug} import DOMAIN, URLS, EXTRACTORS
print('DOMAIN:', DOMAIN)
print('URLS:', URLS)
print('EXTRACTORS:', list(EXTRACTORS.keys()))
"
```

Expected: No import errors, correct domain, URLS paths, and extractor function names.

### 5.2 — Run the monitor for this fund only

```bash
pnpm worker:monitor --slugs {fund-slug}
```

This fetches the fund's website, runs your extractor, and writes output to `data/derived/portfolio_items.json`.

> Do not combine `--limit` with `--slugs` for extractor URL checks. URL limiting is applied before slug filtering, which can exclude your target fund entirely.

### 5.3 — Check the output

```bash
# Count extracted companies
python3 -c "
import json
d = json.load(open('data/derived/portfolio_items.json'))
companies = d.get('fund_portfolios', {}).get('{fund-slug}', [])
print(f'Companies: {len(companies)}')
for c in companies[:5]:
    print(f\"  - {c['name']} ({c.get('status', 'unknown')}) [{c.get('sector', 'no sector')}]\")
"
```

> **CRITICAL**: If this returns 0 companies, either:
> - the fund truly has no public portfolio index (manual/PEM mode is expected), or
> - your `URLS["portfolio"]` is wrong / selectors are broken.
> Do not force `"/"` as a placeholder to silence this check.

### 5.4 — Extractor validation checklist

- [ ] `DOMAIN` matches the domain in `db.json` `website` field **exactly**
- [ ] Every URLS path verified against the live website (returns 200, has content)
- [ ] No template paths like `/investments` or `/management`
- [ ] `extract_portfolio()` returns at least 1 company (for funds with portfolio pages)
- [ ] Company names are real company names (not navigation text, not "Read more", not "Back to top")
- [ ] Company names won't be rejected by `isValidPortfolioEntry()` (see Section 4.3)
- [ ] `status` field is set correctly (`"current"`, `"exited"`, or `None`)
- [ ] Relative URLs resolved with `urljoin(base_url, href)`
- [ ] Confidence scores in range 0.7–0.95
- [ ] Deduplication via `seen_names` set
- [ ] No hardcoded fund names or fund-specific logic that belongs in `db.json` metadata
- [ ] If site uses API/JSON responses: set `ALWAYS_EXTRACT = True`

### 5.5 — Run unit tests

```bash
cd apps/worker && pytest
```

Ensure your new extractor doesn't break existing tests. Test files are in `apps/worker/tests/`. While there's no mandatory test template for new extractors, the test suite includes `test_blocked_fund_extractors.py` which verifies all extractors load correctly.

---

## 6. Run the Pipeline

### 6.1 — Full pipeline for this fund

```bash
pnpm pipeline --slugs {fund-slug}
```

This runs all pipeline steps. The canonical step list and ordering is defined in the `STEPS` list in `apps/worker/fundradar_worker/pipeline.py`. Current steps:

| Step | Script | What it does | Idempotent? |
|---|---|---|---|
| 1. monitor | `monitor.py` | Fetch website, extract portfolio/team/news, detect signals | Yes (content hash) |
| 2. rss | `rss_monitor.py` | Fetch Italian PE/VC RSS feeds, match articles to fund | Yes (state tracking) |
| 3. translate | `translate_signals.py` | Translate Italian/French → English (DeepL → Azure → OpenAI) | Yes (checks `*_original` fields) |
| 4. normalize_sectors | `normalize_sectors.py` | Normalize sectors to canonical taxonomy | Yes |
| 5. normalize_portfolio | `normalize_portfolio_cross_fund.py` | Deduplicate companies across funds | Yes |
| 6. enrich_portfolio | `enrich_portfolio_gemini_full.py` | Fill missing sector/HQ/description (Gemini, optional) | Yes |
| 7. filter | `filter_signals.py` | Quality scoring, geo gate, noise removal, dedup | Yes |
| 8. enrich | `enrich_signals_openai.py` | AI summaries, target_company extraction (OpenAI) | Yes (progress file) |
| 9. signal_to_portfolio | `signal_to_portfolio.py` | Convert deal/exit signals → portfolio entries | Yes (progress file) |

> **RSS signals start automatically**: When you add a fund, RSS signals matching the fund name start appearing automatically at step 2. Italian financial press (BeBeez, Il Sole 24 Ore, Milano Finanza, etc.) articles are matched to funds via text matching and LLM classification. No extractor is needed for RSS — it's entirely automatic.

### 6.2 — If you only updated extractor code

After modifying an existing extractor, you **must** use `--force-extract`:
```bash
pnpm pipeline --slugs {fund-slug} --force-extract
```

Without this flag, the monitor's content hash optimization skips pages whose HTML hasn't changed — meaning your updated extractor code won't run. **Example**: if you fix status detection from `"current"` to `"exited"`, use `--force-extract` even if the HTML was fetched yesterday.

### 6.2.1 — Mandatory backpropagation after `--force-extract`

Extractor fixes can change parsing output without any real website change. That can create pseudo-"new" portfolio/news signals during the first forced run. You must backpropagate those artifacts immediately.

1. Run a focused monitor pass:
   ```bash
   pnpm pipeline --step monitor --slugs {fund-slug} --force-extract
   ```
2. Inspect generated output for the same slug:
   - `data/derived/portfolio_items.json` (company list quality)
   - `data/derived/detected_signals.json` (raw new signals)
   - `data/derived/detected_signals_filtered.json` (what survives quality gates)
3. If the run produced extractor-artifact signals (e.g., nav text, logo labels, or normalization drift), fix the extractor and remove the artifact rows from derived output.
4. Re-run the same focused command until it produces **0 new signals** for that slug.

This prevents extractor-change noise from being mistaken as real deal flow.

### 6.3 — Run individual steps

```bash
# Filter + enrich only (skip fetching)
pnpm pipeline:signals

# Signal-to-portfolio conversion only
pnpm pipeline:signals-to-portfolio

# Specific step only
pnpm pipeline --step filter
```

---

## 7. Enrich Portfolio Data with Gemini

### What it does

Step 6 (`enrich_portfolio_gemini_full.py`) uses **Gemini** with Google Search grounding to fill missing **portfolio company** data:
- Missing sector
- Missing HQ location
- Missing description

> **This enriches PORTFOLIO COMPANY descriptions, NOT the fund itself.** For fund-level descriptions, see [Section 8](#8-generate-fund-description-optional).

### Configuration

Configuration values are defined as constants at the top of `apps/worker/scripts/enrich_portfolio_gemini_full.py`. Key settings:

| Setting | Where defined |
|---|---|
| Model | `MODEL` constant in `enrich_portfolio_gemini_full.py` (currently `gemini-3-flash-preview` — NEVER use any `gemini-2.x`) |
| API Key | `GEMINI_API_KEY` env var |
| Package | `google-genai>=1.0.0` (`from google import genai`) |
| Batch size | `BATCH_SIZE` constant in the script |
| Pipeline cap | `--pipeline` flag default limit |
| Timeout | Defined in `pipeline.py` `STEPS` list |

### When it runs

- **Automatically** as step 6 of `pnpm pipeline`
- **Optional** — auto-skips if `GEMINI_API_KEY` is not set
- Runs AFTER portfolio normalization but BEFORE signal filtering

### Verify the enrichment

```bash
python3 -c "
import json
d = json.load(open('data/derived/portfolio_items.json'))
companies = d.get('fund_portfolios', {}).get('{fund-slug}', [])
enriched = [c for c in companies if c.get('sector') and c.get('description')]
print(f'Total: {len(companies)}, With sector+description: {len(enriched)}')
"
```

---

## 8. Generate Fund Description (Optional)

If the new fund has no `description` in `db.json` (or it's poor quality), you can generate one via Gemini:

```bash
# Script is at the repo ROOT scripts/ directory, not apps/worker/scripts/
python3 scripts/generate-fund-descriptions-gemini.py --slugs {fund-slug}
```

This:
- Uses Gemini with Google Search grounding to research the fund
- Generates an English description based on publicly available information
- Sets `description_source: "gemini"` to track provenance
- Writes the description back to `db.json`

> **This is a fund-level description** (appears in the fund's overview tab), separate from portfolio company descriptions enriched in Step 7.

---

## 9. Audit Portfolio Assets with Gemini

After the pipeline has populated portfolio data and the fund description is generated, run the **Gemini asset audit** to verify and improve data quality. This is the same audit that was run on the original 163 funds.

### What it does

`scripts/audit-fund-assets-gemini.py` uses Gemini 3 Flash to:
- **Verify existing portfolio entries** — detect wrong entries, wrong fields (status, sector, HQ, description)
- **Find missing Italian assets** — identify portfolio companies the fund holds in Italy that weren't extracted
- **Suggest fund metadata corrections** — HQ city, description, website fixes

### Run the audit

```bash
# Single fund (recommended stable settings)
python3 scripts/audit-fund-assets-gemini.py \
  --slugs {fund-slug} \
  --no-grounding \
  --chunk-size 20 \
  --chunk-split-sizes 20,8,1 \
  --max-existing-names-in-missing-prompt 60 \
  --missing-name-caps 60,20,1 \
  --sleep-seconds 1 \
  --timeout-sec 90 \
  --hard-timeout-sec 120 \
  --retries 3

# Multiple funds
python3 scripts/audit-fund-assets-gemini.py \
  --slugs fund-a,fund-b,fund-c \
  --no-grounding \
  --chunk-size 20 \
  --chunk-split-sizes 20,8,1 \
  --max-existing-names-in-missing-prompt 60 \
  --missing-name-caps 60,20,1 \
  --sleep-seconds 1 \
  --timeout-sec 90 \
  --hard-timeout-sec 120 \
  --retries 3

# Dry run (preview, no API calls)
python3 scripts/audit-fund-assets-gemini.py --slugs {fund-slug} --dry-run
```

For large queues (resume-safe shards), prefer:

```bash
python3 scripts/run-audit-fund-assets-gemini-parallel.py \
  --workers 4 \
  --no-grounding \
  --chunk-size 20 \
  --chunk-split-sizes 20,8,1 \
  --max-existing-names-in-missing-prompt 60 \
  --missing-name-caps 60,20,1 \
  --sleep-seconds 1 \
  --timeout-sec 90 \
  --hard-timeout-sec 120 \
  --retries 3
```

### Apply audit findings

After the audit completes, review the output in `data/derived/gemini_fund_asset_audit.json`, then apply confirmed findings:

```bash
pnpm pipeline:new-fund-quality --slugs {fund-slug} --apply-missing-assets
```

This:
- Reads the audit results from `gemini_fund_asset_audit.json`
- Inserts missing companies into `portfolio_items.json`
- Marks inserted entries as `curation_locked` (prevents future overwrite)
- Respects manual review decisions (reject/ready)

### Optional: Verify Gemini-enriched entries

For entries added via Gemini (not from website extraction), verify them against Google Search:

```bash
python3 scripts/verify-portfolio-gemini.py --slugs {fund-slug}
```

### Output files

| File | Purpose |
|---|---|
| `data/derived/gemini_fund_asset_audit.json` | Audit results per fund |
| `data/derived/gemini_fund_asset_audit_progress.json` | Progress tracking (resume support) |

> **Cost**: ~1-3 Gemini API calls per fund (free tier handles this). The script paces calls at 3s intervals with retry/backoff.

---

## 10. Enrich Fund Metadata with Gemini

### What it does

Uses **Gemini 3 Flash** with Google Search grounding to fill missing metadata fields in `db.json`:

- **`aum_eur`** — Assets Under Management in EUR
- **`investment_min_eur`** — Minimum ticket size in EUR
- **`investment_max_eur`** — Maximum ticket size in EUR

The script only updates fields that are currently `null` — it never overwrites existing values.

### Running the script

```bash
# Enrich a specific fund (after adding it):
python3 scripts/enrich-fund-metadata-gemini.py --slugs cherry-bay-capital

# Enrich all funds missing AUM:
python3 scripts/enrich-fund-metadata-gemini.py --missing-aum

# Enrich all funds missing investment ranges:
python3 scripts/enrich-fund-metadata-gemini.py --missing-ranges

# Dry run (show what would be updated):
python3 scripts/enrich-fund-metadata-gemini.py --slugs cherry-bay-capital --dry-run
```

### How it works

1. Queries Gemini with Google Search grounding for each fund
2. Validates responses: AUM range €1M–€2T, investment range €10K–€10B
3. Returns `null` for unverifiable data (no hallucinated figures)
4. Writes directly to `db.json` (atomic via `safe_json_write()`)

### Output files

| File | Purpose |
|---|---|
| `data/db.json` | Updated with AUM and investment range fields |
| `data/derived/fund_metadata_enrichment_progress.json` | Progress tracking (resume support) |

### Validation

After running, spot-check a few values against the source URLs logged in the output:

```bash
# Check AUM coverage:
python3 -c "import json; funds=json.load(open('data/db.json'))['funds']; print(f'Missing AUM: {len([f for f in funds if not f.get(\"aum_eur\")])}/{len(funds)}')"
```

> **Cost**: 1 Gemini API call per fund (free tier). The script paces calls at 3s intervals with retry/backoff. Temperature is set to 0.2 for factual accuracy.

---

## 11. Enrich Signals with OpenAI

### What it does

Step 8 (`enrich_signals_openai.py`) uses **OpenAI** to:
- Generate English AI summaries (`enriched_summary`) for each signal
- Extract `target_companies` from deal/exit signals (used by step 9)
- Apply safety-net translation for any Italian that survived step 3

### Configuration

Configuration values are defined as constants in `apps/worker/scripts/enrich_signals_openai.py`:

| Setting | Where defined |
|---|---|
| Model | `MODEL` constant (currently `gpt-5.4-mini` — NEVER use ChatGPT 4o, it hallucinates) |
| Concurrent requests | `MAX_CONCURRENT_LLM` constant |
| Rate limit | `REQUESTS_PER_MINUTE` constant |
| Progress file | `signal_enrichment_progress.json` |

### Cost control (CRITICAL)

- **NEVER delete `signal_enrichment_progress.json`** — forces full re-enrichment (several dollars in API costs)
- **NEVER delete `detected_signals_enriched.json`** — forces re-translation of all Italian signals
- For debugging: edit `detected_signals_enriched.json` directly (free) instead of re-running the enricher
- See `apps/worker/CLAUDE.md` "OpenAI Cost Control" section for full rules and current cost estimates

### enriched_summary coverage

**~40-60% of signals will have `enriched_summary=""`** — this is intentional, NOT a bug. When the LLM summary is 85%+ word overlap with the title, it's cleared. The frontend falls back to displaying the title — this is correct behavior, not data loss.

### Signal quality issues

If signals are showing the wrong type, bad text, wrong fund attribution, missing from the website, or not generating portfolio entries — see **[`/docs/check_signals.md`](/docs/check_signals.md)** for the full diagnostic guide. It covers all 15 issue categories with the exact function and file to fix for each.

---

## 12. AIFI Data Merge (Optional)

If the fund is an AIFI member and you want to pull in AIFI metadata (AUM, investment ranges, contact info, geocoded offices):

```bash
# Step 1: Scrape latest AIFI data (optional — skip if AIFI data is already fresh)
pnpm worker:aifi

# Step 2: Merge AIFI data into db.json
pnpm merge-aifi
```

`merge-aifi` (`scripts/merge-aifi-metrics.ts`) merges into `db.json`:
- `aum_eur`, `num_funds`, `num_portfolio_companies`
- `investment_min_eur`, `investment_max_eur`
- `contact_name`, `contact_email`, `contact_phone`
- `aifi_url`
- Office locations and coordinates (if geocoded)

**Shortcut**: `pnpm aifi:full` runs both scrape + merge in sequence.

> **Warning**: AIFI scraper sets wrong HQ for global funds — the Italian branch gets written as HQ. After ANY AIFI merge, cross-check `offices[]` `is_hq` entries against top-level `hq_*` fields. Preserve the Italian office in `offices[]` when fixing the global HQ.

---

## 13. Geocoding & Map (Optional)

Without geocoded coordinates, the fund **won't appear on the `/map` page**. To add coordinates:

```bash
# Step 1: Geocode addresses (uses Nominatim/OpenStreetMap — free, 1 req/sec)
pnpm worker:geocode

# Step 2: Merge coordinates into db.json
pnpm merge-aifi
```

This populates `hq_lat`, `hq_lng`, and `hq_address` in `db.json`. The map page resolves coordinates in this priority:
1. `offices[]` array (prefers Italian office → HQ → any office with lat/lng)
2. `hq_lat` / `hq_lng` fields
3. `cityCoordinates.ts` fallback (~59 entries covering Italian and European cities, matched by `hq_city` name)

### Address quality rule (MANDATORY for Italy offices)

- If a fund has an office in Italy, never leave a generic city-only address like `Milan`, `Rome`, or `Italy`.
- `hq_address` / `offices[].address` must be specific (street + number, and city at minimum) whenever that office is in Italy.
- This resolution step is owned by the automation/agent workflow, not by manual user follow-up.
- Resolve the address with a quick web lookup first (official site/contact/legal pages). If unclear, use a Gemini API lookup to extract/verify the address and write it directly to `db.json`.
- If still unresolved after both attempts, do **not** invent an address: explicitly report the blocker (fund slug, attempted sources, why unresolved) and request input only as last resort.

Quick audit before commit (find Italian offices still using generic addresses):

```bash
python3 -c "
import json, re
db = json.load(open('data/db.json'))
GENERIC = {'milan','milano','rome','roma','italy','italia'}

def is_generic(address, city, country):
    if not address:
        return True
    a = address.strip().lower()
    if a in GENERIC:
        return True
    if city and a == city.strip().lower():
        return True
    if country and a == country.strip().lower():
        return True
    if not any(ch.isdigit() for ch in a):
        tokens = [t.strip() for t in re.split(r'[,/;-]+', a) if t.strip()]
        allowed = {x.lower() for x in [city, country, 'italy', 'italia'] if x}
        if tokens and set(tokens).issubset(allowed):
            return True
    return False

for f in db.get('funds', []):
    slug = f.get('slug')
    city = f.get('hq_city')
    country = f.get('hq_region')
    hq_address = f.get('hq_address')
    if (country or '').lower() == 'italy' and is_generic(hq_address, city, country):
        print(f'{slug}: generic hq_address -> {hq_address!r}')
    for off in f.get('offices', []) or []:
        if (off.get('country') or '').lower() != 'italy':
            continue
        if is_generic(off.get('address'), off.get('city'), off.get('country')):
            print(f'{slug}: generic office address -> {off.get(\"address\")!r}')
"
```

---

## 14. Verify Frontend Display

### 14.1 — Restart the dev server

The web app caches all JSON data in memory with **NO TTL, NO invalidation**. After any worker run:

```bash
pnpm dev
```

### 14.2 — Check the fund pages

| URL | What to check |
|---|---|
| `http://localhost:3000` | Fund appears in the home table |
| `http://localhost:3000/funds/{slug}` | Fund detail page loads |
| Overview tab | Name, category, AUM, strategy, sectors display correctly |
| Portfolio tab | Companies listed with correct names, sectors, and statuses |
| Signals tab | Signals appear (if any were detected) |
| Deals tab | PEM deals appear (if any exist) |
| `http://localhost:3000/map` | Fund appears on the map (if geocoded) |
| `http://localhost:3000/companies` | Portfolio companies appear |
| `http://localhost:3000/signals` | Fund's signals appear in the global feed |

### 14.3 — Data loading architecture

Understanding how data reaches the UI (verify against `apps/web/src/lib/data.ts` if this seems outdated):

```
db.json ──────────────→ data.ts:loadDatabase() ──→ Fund list, fund detail overview
portfolio_items.json ──→ data.ts:getPortfolioForFund() ──→ Portfolio tab (merges website + PEM)
pem_deals.json ────────→ data.ts:getDealsForFund() ──→ Deals tab
detected_signals_filtered.json → data.ts:getSignalsForFund() ──→ Fund detail signals tab
detected_signals_enriched.json → signals_unified.ts:loadUnifiedSignals() ──→ /signals feed page
```

**Static generation**: Fund pages are pre-rendered at build time via `generateStaticParams()`. The fund's slug is automatically included because `generateStaticParams()` reads all slugs from `db.json`.

---

## 15. Sitemap & llms.txt (Automatic)

### Sitemap

**File**: `apps/web/src/app/sitemap.ts`

The sitemap is **generated automatically** at build time. It reads all fund slugs from `db.json` and all company slugs. No manual action needed — your new fund is automatically included.

### llms.txt

**Files**: `apps/web/src/app/llms.txt/route.ts` and `apps/web/src/app/llms-full.txt/route.ts`

These are dynamic route handlers that generate the `/llms.txt` and `/llms-full.txt` endpoints at request time. They read live stats (fund count, signal count, portfolio company count) from `data.ts` and `signals_unified.ts`.

**No manual action needed** — the stats automatically update to include your new fund and its signals/portfolio companies. The llms.txt files inform AI models about the site's content and when to recommend Fundradar.

---

## 16. Assets & OG Images (Automatic)

### OG Images

**File**: `apps/web/src/app/opengraph-image.tsx`

A site-level OG image (1200x630 PNG) is generated at the edge. There is no per-fund OG image — all fund pages share the same site-level OG image. **No manual action needed.**

### Logos

There is no centralized logo storage. Fund logos are referenced from the fund's own website during extraction (if available). The system does not host or manage fund logos separately.

---

## 17. Commit & Deploy

### 17.1 — What to commit

```bash
# Stage the new/modified files
git add data/db.json
git add apps/worker/fundradar_worker/strategies/extractors/{fund_slug}.py
git add data/derived/portfolio_items.json
git add data/derived/detected_signals_filtered.json
git add data/derived/detected_signals_enriched.json
```

**Do NOT commit:**
- `signal_enrichment_progress.json` (progress tracker, not data)
- `signal_to_portfolio_progress.json` (progress tracker, not data)
- `url_status.json` (transient state)
- `deepl_quota_state.json` (transient state)
- `rss_state.json` (transient state)

### 17.2 — Commit message

```
Add {Fund Name} fund and extractor

- Domain: {domain}
- Portfolio page: {path}
- {N} companies extracted
- News monitoring: {enabled/disabled}
```

### 17.3 — Deploy

Fundradar auto-deploys from `main` on Vercel:

1. Push to `main`
2. Vercel builds the Next.js app from `apps/web/`
3. `generateStaticParams()` pre-renders the new fund page
4. Live at `fundradar.co/funds/{slug}` within ~2 minutes

---

## 18. Verify Data Quality (MANDATORY)

This is a **mandatory** verification step. Do NOT consider the fund "done" until all checks pass.

### 18.0 — Mandatory One-Command Workflow

Run this command for every added/changed fund before commit:

```bash
pnpm pipeline:new-fund-quality --slugs {fund-slug}
```

Recommended for full remediation (includes missing-asset apply):

```bash
pnpm pipeline:new-fund-quality --slugs {fund-slug} --apply-missing-assets
```

Batch remediation for all newly-added/outlier funds:

```bash
pnpm pipeline:new-fund-quality --auto-detect-new --apply-missing-assets
```

### 18.0.1 — Network Preflight (avoid sandbox DNS failures)

This workflow is network-heavy (fund websites + Gemini API). If DNS/network is restricted, quality checks will fail for the wrong reason.

Quick preflight:

```bash
python3 - <<'PY'
import socket
for host in ['generativelanguage.googleapis.com', 'www.blackstone.com', 'bebeez.it']:
    try:
        socket.getaddrinfo(host, 443)
        print('OK ', host)
    except Exception as e:
        print('FAIL', host, '-', e)
PY
```

If any host fails, run outside DNS-restricted sandbox mode.  
`pipeline:new-fund-quality` now performs this preflight automatically and fails fast with a clear error.

### 18.0.2 — Manual Gemini Prompts (copy/paste fallback)

If automation is blocked (DNS/sandbox/API outage) or you want a second opinion on a specific fund page, use these prompts directly in Gemini and paste the result back into your review notes.

Rules:
- Always ask for **English-only output**.
- Require **source URLs** for every factual claim.
- Treat Gemini output as audit input, not auto-truth: only apply changes if sources are credible and Italy-relevant.

Prompt A — fund page quality/completeness audit:

```text
You are auditing a private-markets fund profile for Italy relevance and data quality.

Fund name: {FUND_NAME}
Fund slug: {FUND_SLUG}
AUM (EUR): {AUM_EUR_OR_UNKNOWN}

Current Fundradar snapshot:
- Italy portfolio count: {ITALY_PORTFOLIO_COUNT}
- Signals count: {SIGNAL_COUNT}
- Portfolio entries (paste top entries here):
{PORTFOLIO_SNIPPET}
- Signals shown on page (paste recent signals here):
{SIGNALS_SNIPPET}

Task:
1) Identify factual inaccuracies, missing major Italy assets, weak/irrelevant signals, and non-English or malformed text.
2) Flag anything not Italy-relevant that should not be on the Italy feed.
3) Suggest only concrete fixes that are systemic (would hold on future pipeline runs), not one-off wording tweaks.
4) Keep output short and direct.

Output JSON only:
{
  "overall_status": "ok|needs_fixes|highly_incomplete",
  "critical_issues": [{"type":"...", "detail":"...", "why_it_matters":"..."}],
  "missing_italy_assets": [{"name":"...", "status":"current|exited", "why":"...", "sources":["https://..."]}],
  "signal_issues": [{"signal_or_pattern":"...", "issue":"...", "fix_direction":"..."}],
  "systemic_fix_recommendations": [{"layer":"extractor|filter|enrichment|signal_to_portfolio|normalizer", "action":"..."}]
}

Constraints:
- English only.
- Include source URLs for every asset or factual correction.
- Do not invent data.
```

Prompt B — specific fund Italy-presence validation (fast check):

```text
Validate whether this fund is materially active in Italy and whether the following summary looks incomplete.

Fund: {FUND_NAME}
Known Fundradar summary:
{PASTE_CURRENT_SUMMARY_OR_PAGE_TEXT}

Return:
1) A yes/no on "materially active in Italy".
2) Top 5 Italy-relevant assets/deals that should appear (if missing), with year and source URL.
3) Short verdict: "all good" or "incomplete".

Constraints:
- English only.
- Only factual claims with source URLs.
- Prefer official fund sites and reputable financial press.
```

Prompt C — generate candidate historical signals for page completeness:

```text
For fund {FUND_NAME}, propose up to 5 Italy-relevant historical events suitable for an Italy private-markets signals feed.

For each event provide:
- signal_type (investment|exit|people|fund|portfolio|debt|partnership)
- concise title (single sentence, English)
- what_changed (1-2 sentences, factual)
- event_date (YYYY-MM-DD if known)
- source_name
- source_url
- italy_relevant_reason

Hard constraints:
- No boilerplate language.
- No non-Italy events.
- No duplicate events.
- Do not output events without verifiable source URLs.
```

Example (ICG quick check): use Prompt B with `Fund: ICG (Intermediate Capital Group)` and paste the current ICG fund page content.

What this does:
- runs pipeline (+ force extract by default)
- runs Gemini portfolio enrichment
- runs Gemini metadata enrichment
- runs Gemini fund-asset audit
- runs signal-to-portfolio sync
- runs completion verifier
- applies top-AUM historical backfill and re-verifies
- writes summary JSON to `data/derived/new_fund_quality_pipeline_summary.json`

Use the manual sub-steps below only for debugging/recovery.

### 18.1 — Automated data check

Run this verification script for every new fund before committing:

```bash
python3 -c "
import json

slug = '{fund-slug}'
db = json.load(open('data/db.json'))
fund = next((f for f in db['funds'] if f['slug'] == slug), None)
portfolio = json.load(open('data/derived/portfolio_items.json'))
companies = portfolio.get('fund_portfolios', {}).get(slug, [])
filtered = json.load(open('data/derived/detected_signals_filtered.json')).get('signals', [])
enriched = json.load(open('data/derived/detected_signals_enriched.json')).get('signals', [])
filtered_rows = [s for s in filtered if s.get('fund_slug') == slug]
enriched_rows = [s for s in enriched if s.get('fund_slug') == slug]

errors = []

# 1. db.json fields
if not fund:
    errors.append('FATAL: Fund not in db.json')
else:
    if not fund.get('description'):
        errors.append('Missing description')
    if not fund.get('website'):
        errors.append('Missing website')
    if not fund.get('aum_eur'):
        errors.append('Missing AUM (run enrich-fund-metadata-gemini.py)')
    if not fund.get('geographies'):
        errors.append('Missing geographies')
    if not fund.get('strategy_tags'):
        errors.append('Missing strategy_tags')

# 2. Portfolio count
if len(companies) == 0:
    errors.append('CRITICAL: Zero portfolio entries — check extractor URLS[\"portfolio\"]')
elif len(companies) < 3:
    errors.append(f'WARNING: Only {len(companies)} portfolio entries — verify extractor')

# 2b. Portfolio enrichment (sector/desc/HQ)
if len(companies) > 0:
    with_sector = sum(1 for c in companies if c.get('sector'))
    with_desc = sum(1 for c in companies if c.get('description'))
    with_hq = sum(1 for c in companies if c.get('headquarters') or c.get('hq_country'))
    if with_sector < len(companies):
        errors.append(f'ENRICHMENT: {len(companies)-with_sector} companies missing sector — run: cd apps/worker && python3 scripts/enrich_portfolio_gemini_full.py --slugs {slug} --limit 0')
    if with_desc < len(companies):
        errors.append(f'ENRICHMENT: {len(companies)-with_desc} companies missing description — run Gemini enrichment')
    if with_hq < len(companies):
        errors.append(f'ENRICHMENT: {len(companies)-with_hq} companies missing HQ — run Gemini enrichment')

# 3. Extractor URLS
import importlib, sys
sys.path.insert(0, 'apps/worker')
mod_name = slug.replace('-', '_')
try:
    mod = importlib.import_module(f'fundradar_worker.strategies.extractors.{mod_name}')
    urls = getattr(mod, 'URLS', {})
    if urls.get('portfolio') is None:
        if len(companies) == 0:
            errors.append('WARNING: Extractor URLS[\"portfolio\"] is None and no manual/PEM portfolio entries found')
        else:
            errors.append('INFO: Extractor URLS[\"portfolio\"] is None (manual/PEM portfolio mode)')
    if 'portfolio' not in getattr(mod, 'EXTRACTORS', {}):
        errors.append('WARNING: No extract_portfolio() function in EXTRACTORS')
except Exception as e:
    errors.append(f'WARNING: Could not import extractor: {e}')

# 4. Signal misattribution check (first word of fund name)
if fund:
    name_words = fund['name'].lower().split()
    first_word = name_words[0] if name_words else ''
    GENERIC_SHORT = {'capital','partners','private','venture','equity','asset','management','group',
        'fondo','fund','team','cherry','silver','golden','bridge','impact','summit','spring',
        'castle','anchor','global','europe','invest','select','market','search','towers','credit',
        'sviluppo','imprese','centro','italia','italiano','nazionale'}
    if len(name_words) >= 3 and len(first_word) >= 6 and first_word not in GENERIC_SHORT:
        errors.append(f'WARNING: Fund name first word \"{first_word}\" (from 3+ word name) could cause signal misattribution — verify it is in GENERIC_SHORT_BRANDS in signalFundTags.ts or that no cross-entity matches occur')

# 5. Filtered vs enriched signal parity
filtered_by_id = {s.get('id'): s for s in filtered_rows if s.get('id')}
enriched_by_id = {s.get('id'): s for s in enriched_rows if s.get('id')}
missing_in_enriched = sorted(set(filtered_by_id) - set(enriched_by_id))
stale_in_enriched = sorted(set(enriched_by_id) - set(filtered_by_id))
if missing_in_enriched:
    errors.append(f'CRITICAL: {len(missing_in_enriched)} filtered signals missing in enriched (run slug-scoped enrich)')
if stale_in_enriched:
    errors.append(f'CRITICAL: {len(stale_in_enriched)} enriched signals not present in filtered (stale rows; resync enrich from filtered)')

type_mismatches = []
for sid, frow in filtered_by_id.items():
    erow = enriched_by_id.get(sid)
    if not erow:
        continue
    if (frow.get('signal_type') or '') != (erow.get('signal_type') or ''):
        type_mismatches.append((sid, frow.get('signal_type'), erow.get('signal_type')))
if type_mismatches:
    sample = ', '.join(f'{sid}:{ft}->{et}' for sid, ft, et in type_mismatches[:3])
    errors.append(f'CRITICAL: {len(type_mismatches)} signal_type mismatches filtered vs enriched ({sample})')

if errors:
    print(f'VERIFICATION FAILED for {slug}:')
    for e in errors:
        print(f'  ✗ {e}')
else:
    print(f'ALL CHECKS PASSED for {slug}')
    print(f'  Portfolio: {len(companies)} companies')
    print(f'  Signals filtered/enriched: {len(filtered_rows)}/{len(enriched_rows)}')
    print(f'  AUM: {fund.get(\"aum_eur\")}')
    print(f'  Description: {fund.get(\"description\",\"\")[:60]}...')
"
```

Hard-gate verifier (recommended, replaces the ad-hoc inline check above):

```bash
# Auto-detect newly added funds (created_at outliers vs baseline)
pnpm verify:new-fund-completion

# Or verify specific slugs
pnpm verify:new-fund-completion --slugs patrizia,oaktree-capital-management,silver-lake
```

This command fails (`exit 1`) if any fund is incomplete on mandatory gates:
- missing AUM/description/strategy/geographies in `db.json`
- incomplete portfolio enrichment (sector/description/HQ coverage)
- missing or non-complete Gemini asset audit result
- filtered/enriched signal parity mismatch
- top-AUM fund below minimum signal completeness threshold
- top-AUM fund with `italian_portfolio_count=0` without verified-zero whitelist

CI hard gate (deterministic, no network) now enforces this on PRs:

```bash
pnpm verify:new-fund-gate --base-ref <base_sha> --head-ref <head_sha>
```

The gate requires updated tracked artifacts in the same diff:
- `data/derived/new_fund_completion_report.json`
- `data/derived/gemini_fund_asset_audit.json`

Run the deterministic internal QA agent right after the check above:

```bash
# Sync actionable deal/exit signals into portfolio status before QA
pnpm pipeline:signals-to-portfolio

# Then run cross-fund deterministic QA
python3 scripts/internal_quality_agent.py
```

Then inspect unresolved high/medium issues for your slug:

```bash
jq -r --arg slug "{fund-slug}" '
  .findings
  | map(select(.fund_slug == $slug and (.severity == "high" or .severity == "medium")))
  | "open_issues=\(length)",
    (.[]
      | "\(.severity) \(.category) \(.signal_id // "-") :: \(.evidence)")
' data/derived/internal_agent_audit.json
```

Acceptance bar for the added fund: `open_issues=0`. If not zero, apply a **systemic code fix** (not one-off JSON edits), rerun affected pipeline steps, and rerun this audit until clean.

### 18.2 — Gemini portfolio enrichment (MANDATORY)

After the pipeline runs, you **MUST** run Gemini portfolio enrichment to fill missing sector/HQ/description on portfolio companies. This is NOT optional — the pipeline's monitor step only extracts what the website provides, which is often incomplete.

```bash
# Run portfolio enrichment for the new fund(s)
cd apps/worker && python3 scripts/enrich_portfolio_gemini_full.py --slugs {fund-slug} --limit 0
```

Then **verify** enrichment was applied:

```bash
python3 -c "
import json
slug = '{fund-slug}'
d = json.load(open('data/derived/portfolio_items.json'))
companies = d.get('fund_portfolios', {}).get(slug, [])
n = len(companies)
with_sector = sum(1 for c in companies if c.get('sector'))
with_desc = sum(1 for c in companies if c.get('description'))
with_hq = sum(1 for c in companies if c.get('headquarters') or c.get('hq_country'))
print(f'Companies: {n}')
print(f'With sector: {with_sector}/{n}')
print(f'With description: {with_desc}/{n}')
print(f'With HQ: {with_hq}/{n}')
if with_sector < n or with_desc < n or with_hq < n:
    print('WARNING: Some companies still missing data — re-run enrichment or check Gemini errors')
else:
    print('ALL COMPANIES FULLY ENRICHED')
"
```

**If enrichment coverage is < 100%**: Re-run with `--limit 0` (unlimited). If specific companies consistently fail, they may need manual data entry in `portfolio_items.json`.

### 18.3 — Gemini metadata enrichment (MANDATORY)

Ensure the fund has AUM and investment ranges:

```bash
python3 scripts/enrich-fund-metadata-gemini.py --slugs {fund-slug}
```

### 18.4 — Gemini asset audit (MANDATORY)

Run the asset audit to find missing Italian companies and verify data accuracy:

```bash
python3 scripts/audit-fund-assets-gemini.py \
  --slugs {fund-slug} \
  --no-grounding \
  --chunk-size 20 \
  --chunk-split-sizes 20,8,1 \
  --max-existing-names-in-missing-prompt 60 \
  --missing-name-caps 60,20,1 \
  --sleep-seconds 1 \
  --timeout-sec 90 \
  --hard-timeout-sec 120 \
  --retries 3
```

Then apply findings:
```bash
pnpm pipeline:new-fund-quality --slugs {fund-slug} --apply-missing-assets
```

### 18.4.1 — If Gemini Chat Works But API Script Fails

This is usually a **format/reliability issue**, not a permissions issue.

Typical causes:
- API flow requires strict machine-parseable JSON; chat UI tolerates formatting noise.
- Prompts become too large (many portfolio names/entries), increasing malformed JSON risk.
- Grounding (`google_search`) can add unstable response wrappers.
- Long-running audits get interrupted mid-run (local stop/timeout), leaving partial coverage.

Required mitigation order:
1. Re-run with the stable command above (`--no-grounding`, smaller chunk sizes, smaller name caps).
2. If still failing, use per-fund manual prompts and import flow:
   `generate-gemini-manual-fund-prompts.py` → save `manual_responses/<slug>.json` → `import-manual-gemini-fund-responses.py` → `rebuild-gemini-audit-from-canonical.py`.
3. Never run manual import and rebuild concurrently; run them sequentially to avoid race/overwrite on canonical JSONL.

> **CRITICAL — `rebuild-gemini-audit-from-canonical.py` WIPES API RUN DATA**
>
> `rebuild-gemini-audit-from-canonical.py` completely replaces `gemini_fund_asset_audit.json` using only the canonical JSONL as source.
> The canonical JSONL contains only AI Studio manual exports — **API runs (via `audit-fund-assets-gemini.py`) are NOT written to the JSONL.**
>
> **Do NOT run `rebuild-gemini-audit-from-canonical.py` if `gemini_fund_asset_audit.json` already contains good API run data.**
> The rebuild is for disaster recovery only (when the output file is corrupted or lost entirely).
>
> Safe workflow when patching a single fund via manual import while the rest of the audit is from API runs:
> 1. Run `import-manual-gemini-fund-responses.py` (updates JSONL only — audit JSON is untouched) ✓
> 2. Re-run `audit-fund-assets-gemini.py --slugs <the-problem-slug>` to merge the manual data into the live audit JSON ✓
> 3. **Do NOT run `rebuild-gemini-audit-from-canonical.py`** ✗

### 18.4.2 — After the audit: check if the fund should be hidden

After the Gemini asset audit completes, check whether the fund qualifies as "confirmed zero-Italy":

```bash
python3 -c "
import json
slug = 'YOUR-SLUG'
audit = json.loads(open('data/derived/gemini_fund_asset_audit.json').read())
f = next((x for x in audit['funds'] if x['slug'] == slug), None)
if f:
    print('completion_ready:', f.get('completion_ready'))
    print('italian_portfolio_count:', f.get('italian_portfolio_count'))
    print('missing_assets:', len(f.get('missing_assets') or []))
"
```

If all three are `True / 0 / 0`, the fund has **no Italian assets** and should be hidden from the website:

1. Add the slug to `data/derived/gemini_fund_asset_zero_italy_verified.json` → `verified_slugs[]`
2. The web filter in `getAllFunds()` (implementation pending — see `apps/web/CLAUDE.md`) will exclude it from all pages automatically

Do NOT hide funds without a complete audit (`completion_ready=False`). The whitelist is the authoritative gate — a fund with 0 portfolio entries that hasn't been audited stays visible.

### 18.5 — Verification loop (MANDATORY for ALL additions)

After running all enrichments, you MUST verify the complete data quality. This applies to **every** fund addition, not just batch additions.

1. **Run the automated data check** (18.1) for ALL new funds
2. **Fix any issues** found (missing portfolio URLs, empty URLS, missing metadata)
3. **Re-run the pipeline** for fixed funds: `pnpm pipeline --slugs {fixed-slugs} --force-extract`
4. **Re-run Gemini portfolio enrichment** (18.2) — verify coverage is 100% or explain gaps
5. **Re-run Gemini metadata enrichment** (18.3) — verify AUM is set
6. **Re-run Gemini asset audit** (18.4) — apply findings
7. **Re-run the automated data check** — repeat steps 2-7 until ALL funds pass
8. **Check signal misattribution** — load the fund page in the dev server, verify signals tab shows only relevant signals

**Do NOT commit until the verification loop produces zero errors.** Common issues:

| Issue | Fix |
|---|---|
| Zero portfolio entries | If a real public portfolio page exists: add `portfolio` URL + extractor. If not: keep `portfolio=None` and add manual/PEM portfolio entries. |
| Missing AUM | Run `enrich-fund-metadata-gemini.py --slugs {slug}` |
| Missing description | Run `generate-fund-descriptions-gemini.py --slugs {slug}` |
| Extractor URLS["portfolio"] is None | Verify whether the fund has a real public portfolio page. If yes, add it; if no, keep manual/PEM mode (do not use homepage placeholder `/`). |

### 18.6 — Italy Feed Policy (STRICT)

The main `/signals` Italy feed is **Italy-strict** for non-Italian/global funds:

- For `mixed_or_global` and `europe_wide` funds, Europe-only evidence is not enough.
- A signal must have **explicit Italy evidence** (Italy/Italian geography/entity evidence in text or extracted metadata).
- Examples that should be filtered from the main feed:
  - Germany-only transactions
  - UK/Nordic-only portfolio updates
  - Pan-European items with no Italy mention

This is enforced in worker geo relevance gates, not by one-off JSON edits.

### 18.7 — Top-AUM Signal Completeness (MANDATORY)

For top-AUM funds, page completeness is mandatory even if recent live signals are sparse:

- Target set: top 25 funds by `aum_eur`
- Minimum: at least 2 visible signals per fund
- If below minimum, add vetted historical Italy-relevant signals through:

Recency policy:
- **Do not drop a signal only because it is old.**
- Valuable historical Italy-relevant signals are valid and should remain visible.
- Filtering/enrichment must use quality + relevance, not age cutoffs.

```bash
# Dry run
python3 scripts/backfill_top_aum_signals.py --top-n 25 --min-signals 2

# Apply
pnpm signals:backfill-top-aum
```

Backfilled signals must:
- be Italy-relevant (explicit evidence in title/body)
- include source URL and source name
- be written to both filtered and enriched files (ID parity)

### 18.8 — Persistence rule (MANDATORY)

If a bad signal/tag/classification appears, do not apply one-off data-only fixes as the final solution.

- Always patch the underlying logic in worker/web code (`filter_signals.py`, `signal_text_utils.py`, `signalFundTags.ts`, `signalProcessing.ts`) so the same bug cannot reappear on the next run.
- Use derived JSON edits only as temporary cleanup/backfill after the code fix.
- Re-run focused pipeline steps (`monitor`/`filter`/`enrich`) for affected slugs and verify the issue stays fixed on a clean rerun.
- Document the rule change in this file (or `docs/runbook.md`) when it introduces a new recurring guardrail.

---

## 19. Post-Deployment Checklist

- [ ] Fund appears on `fundradar.co`
- [ ] Fund detail page loads at `fundradar.co/funds/{slug}`
- [ ] Portfolio tab shows companies
- [ ] Signals tab shows signals (if any)
- [ ] Fund appears on `/map` (if geocoded — see [Section 13](#13-geocoding--map-optional))
- [ ] Fund's companies appear on `/companies`
- [ ] Page renders correctly when shared on social media (site-level OG image is automatic)
- [ ] Run `pnpm audit:quality` to check the fund's data quality grade
- [ ] Clear gap detector dedup state if the fund's name appeared in earlier signals (see §3.6)
- [ ] RSS feeds will automatically match articles mentioning this fund (no action needed)

---

## Reference: db.json Field Catalog

### Required Fields

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique identifier (usually same as slug) |
| `slug` | `string` | URL-safe identifier (lowercase, hyphens) |
| `name` | `string` | Display name (brand name, NOT legal entity name) |
| `category` | `string` | Fund category (see `FundCategory` in `packages/shared/src/types.ts`) |
| `hq_city` | `string \| null` | Headquarters city |
| `hq_region` | `string \| null` | Headquarters region/country |
| `website` | `string \| null` | Official website URL |
| `strategy_tags` | `string[]` | Investment strategies (e.g., `["Buy-Out", "Growth"]`) |
| `sector_tags` | `string[]` | Sector focus areas (e.g., `["Technology", "Healthcare"]`) |
| `description` | `string \| null` | Fund description |
| `created_at` | `string` | ISO timestamp of creation |
| `updated_at` | `string` | ISO timestamp of last update |

### Common Optional Fields

| Field | Type | Description | Common mistake |
|---|---|---|---|
| `geographies` | `string[]` | Target geographies (e.g., `["Europe", "Italy"]`) | |
| `average_investment` | `string[]` | Investment size ranges (e.g., `["€50-100m"]`) | |
| `asset_class` | `string[]` | Asset classes (e.g., `["Private equity"]`) | |
| `aum_eur` | `number \| null` | AUM in EUR | NOT `aum` |
| `num_funds` | `number \| null` | Number of funds managed | |
| `num_portfolio_companies` | `number \| null` | Number of portfolio companies | |
| `investment_min_eur` | `number \| null` | Minimum ticket size in EUR | NOT `investment_min` |
| `investment_max_eur` | `number \| null` | Maximum ticket size in EUR | NOT `investment_max` |
| `contact_name` | `string \| null` | Primary contact person | |
| `contact_email` | `string \| null` | Contact email | |
| `contact_phone` | `string \| null` | Contact phone | |
| `linkedin_url` | `string \| null` | Fund's LinkedIn page | |

### Metadata Fields

| Field | Type | Description |
|---|---|---|
| `data_source` | `string` | Data provenance (`"aifi_scraped"`, `"pem_extracted"`, `"manual"`) |
| `data_confidence` | `string` | Confidence level (`"high"`, `"medium"`, `"low"`) |
| `description_source` | `string` | Where description came from (`"gemini"`, `"manual"`) |
| `is_ecosystem_newsroom` | `boolean` | News page covers the whole market (rare — search db.json for current list) |
| `offices` | `Office[]` | Array of office locations with coordinates (see structure below) |
| `aliases` | `string[]` | Alternative names |
| `aifi_url` | `string` | AIFI member page URL |

### Geocoding Fields

| Field | Type | Description |
|---|---|---|
| `hq_lat` | `number \| null` | Latitude |
| `hq_lng` | `number \| null` | Longitude |
| `hq_address` | `string \| null` | Full address |

These are populated by `pnpm worker:geocode && pnpm merge-aifi`. Without them, the fund won't appear on the map.

### `Office` object structure

Each entry in `offices[]` has:

| Field | Type | Description |
|---|---|---|
| `city` | `string` | City name |
| `country` | `string` | Country name (e.g. `"Italy"`, `"United Kingdom"`) |
| `address` | `string \| null` | Street address (required for Italy — see §13 address quality rule) |
| `postal_code` | `string \| null` | Postal/ZIP code |
| `phone` | `string \| null` | Office phone number |
| `lat` | `number \| null` | Latitude (populated by geocoder) |
| `lng` | `number \| null` | Longitude (populated by geocoder) |
| `is_hq` | `boolean` | `true` for the fund's headquarters office |
| `is_italy` | `boolean` | `true` for Italian offices |
| `source_url` | `string \| null` | Source page where this office was found |
| `source_name` | `string \| null` | Name of the source (e.g. `"AIFI"`, `"fund website"`) |

**At least one entry should have `is_hq: true`.** The map page resolves coordinates in this priority: Italian office with lat/lng → `is_hq: true` entry → any entry with lat/lng → top-level `hq_lat`/`hq_lng` fallback.

> **AIFI warning**: After any AIFI merge, cross-check `offices[].is_hq` against top-level `hq_city`/`hq_region` — AIFI writes Italian branch as HQ for global funds. Preserve the Italian office entry but fix `is_hq` so it reflects the fund's actual global headquarters.

---

## Reference: Extractor Template & Patterns

### Template

The full template is at `apps/worker/fundradar_worker/strategies/extractors/_template.py`. Copy it and customize:

```bash
cp apps/worker/fundradar_worker/strategies/extractors/_template.py \
   apps/worker/fundradar_worker/strategies/extractors/{fund_slug}.py
```

Key imports you'll need:
```python
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json  # If parsing JSON API responses
import re    # If using regex for cleanup
```

### Example: Real extractor (Abenex)

See `apps/worker/fundradar_worker/strategies/extractors/abenex.py` for a production example with:
- Portfolio extraction using `data-statut` attribute for status detection (Italian values — use whatever the site uses)
- Team extraction with role classification
- News extraction from WordPress REST API with HTML fallback (try `json.loads()` first)
- Deduplication via `seen_names` set
- Real estate filtering via strategy keywords

### Pattern: WordPress REST API news

Many fund websites use WordPress. Instead of parsing HTML, fetch the JSON API:

```python
URLS = {
    "news": "/wp-json/wp/v2/posts?per_page=20&_fields=id,title,date,link,excerpt",
}

ALWAYS_EXTRACT = True  # API data changes even when HTML shell doesn't

def extract_news(html: str, base_url: str) -> list[dict]:
    news = []
    try:
        posts = json.loads(html)
        if isinstance(posts, list):
            for post in posts:
                title = post.get("title", {}).get("rendered", "")
                # ... parse structured JSON
                news.append({...})
            return news
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: HTML parsing
    soup = BeautifulSoup(html, "html.parser")
    # ...
```

### Pattern: Multiple portfolio pages (current + exited)

```python
URLS = {
    "portfolio": ["/portfolio/current/", "/portfolio/realized/"],
}

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    # Determine status from URL or page content
    # The monitor calls this function once per URL in the list
    # Use page structure to determine if this is current or exited page
    ...
```

---

## Reference: Common Pitfalls

### During extractor development

| Pitfall | Solution |
|---|---|
| Using template paths (`/investments`, `/management`) | Always verify paths against the live website |
| `DOMAIN` doesn't match `db.json` website | Copy the exact domain from `db.json` — this is the #1 "extractor doesn't run" cause |
| Keyword-based status detection (`"exit" in text`) | Use structural detection (data attributes, section headers) |
| Forgetting `urljoin()` for relative URLs | Always use `urljoin(base_url, href)` for any relative link |
| Extracting nav text as company names | Use specific selectors; frontend's `isValidPortfolioEntry()` silently rejects these |
| Hardcoding fund-specific logic in pipeline code | Put fund metadata flags in `db.json` (e.g., `is_ecosystem_newsroom`) |
| API-based site doesn't refresh | Set `ALWAYS_EXTRACT = True` to bypass content hash check |
| Website blocks automated access (403/blank page) | Check `domain_policies.json`; if site needs JS rendering set `requires_headless`; if site blocks all bots (ShieldPRO, etc.) use manual portfolio entries |

### During pipeline execution

| Pitfall | Solution |
|---|---|
| Updated extractor code doesn't run | Use `--force-extract` to bypass content hash caching |
| `--force-extract` creates fake "new company" signals after parser changes | Backpropagate immediately: tighten extractor filters, clean artifact rows in derived files, and rerun focused monitor until it returns 0 new signals |
| Signals are in Italian after filtering | Translation (step 3) must run BEFORE filter (step 7) — never change this order |
| Deleting progress files | NEVER delete `signal_enrichment_progress.json` or `detected_signals_enriched.json` — causes expensive re-runs. See `apps/worker/CLAUDE.md` for full cost details. |
| UI doesn't show new data | Restart `pnpm dev` — the web app caches with no invalidation |
| Portfolio entries show as garbage | Check `isValidPortfolioEntry()` in `data.ts` — NAV_PATTERNS reject navigation text |
| Signal text expands `CDP` to long legal form | Keep acronym form. Cleaning removes redundant `CDP (...)` parentheticals in both worker and web display paths; if it reappears, update shared regex in `signal_text_utils.py` and `signalProcessing.ts` |
| Merger headline appears as Exit | Treat merger/fusion (`merge`, `merger`, `fusione`) as `deal_announced` unless there is explicit seller/exit evidence (`sells`, `a vendere`, `exit from portfolio`, etc.) |
| Filtered and enriched disagree on `signal_type` for same signal ID | Treat filtered `signal_type` as authoritative in enricher skip/cached paths and resync enriched rows from filtered IDs after classifier/rule changes |
| `/signals` count differs from filtered count for the same fund | Enforce ID parity: enriched should be a 1:1 projection of filtered for each slug. Re-run slug-scoped `filter` then `enrich`, and remove stale enriched-only IDs |
| Europe-only signal appears in Italy feed for global fund | Main feed policy is strict Italy: require explicit Italy evidence for `mixed_or_global` and `europe_wide` funds; do not treat Germany/UK/Nordic-only as sufficient |
| Top-AUM fund page has 0 signals | Run `python3 scripts/backfill_top_aum_signals.py --top-n 25 --min-signals 2 --apply` with vetted Italy-relevant historical signals (source URL required) |
| Prospective bidders appear as extra fund tags | Suppress inferred related tags for sentence-local speculative contexts (`among interested bidders`, `in the running`, `fra/tra gli interessati`, `vying`, etc.). Keep explicitly provided tags and active-party mentions |
| Team profile cards or role openings show as signals | Static titles like `Name Head of X`, `Name investor relations`, `...Legal & Corporate Affairs Specialist`, and TEAM blurbs like `X is the parent company of Y` are demoted to `other` and filtered. If variants leak through, update `TEAM_ROLE_PROFILE_TITLE_RE` / `ROLE_OPENING_TITLE_RE` / `TEAM_STATIC_CORP_DESC_RE` in `filter_signals.py` and matching guards in `signalProcessing.ts` |
| Departure news appears as Investment | If text has people transition verbs (`steps down`, `leaves`, `resigns`, `appointed`, etc.) with no deal/exit evidence, force `people_move` (worker `correct_deal()` + post-ML correction, web `reclassifySignalType()`) |
| Co-investor names lose capitalization in summaries | Re-capitalize from `extracted_entities`, fund slugs, and title-cased company/fund phrases (`extract_company_like_entities()` + `capitalize_entities()` in worker clean paths) so strings like `capital dynamics`/`miura partners` stay properly cased |
| Target company names stay lowercased (`cyber guru`, `casalini`) | Add `target_companies[].name` as capitalization hints in both filter and enricher cleanup passes so entity-case repairs persist for cached and fresh signals |
| OCR/translation artifacts leak into feed text (`Be Beez`, `Teamsystem`, `Rosari to`) | Patch shared `clean_display_text()` / `fix_spacing()` regex rules in `signal_text_utils.py` instead of editing derived JSON so new runs auto-fix the same pattern family |
| “X invests in Y to accelerate growth” gets tagged as accelerator/fund launch | Keep accelerator detection noun-based (`accelerator/incubator/program/hub`) and avoid matching the verb `accelerate`; then re-run post-ML shared corrections (`apply_type_corrections`) so `invests in` remains `deal_announced` |
| “Join forces” partnership appears as People | Treat `join forces` as partnership in both primary classifier and `detect_all_signal_types()` (secondary badges), unless there is explicit appointment/hire language |
| Fix works once but breaks on next pipeline run | The fix is data-only. Patch worker/web rules first, then rerun pipeline and backfill outputs; one-off JSON cleanup alone is not persistent |
| **Claude Code blocks on long scripts** | **ALWAYS run Gemini/pipeline scripts with `run_in_background: true` and check progress with non-blocking `tail` commands. NEVER use blocking waits (`block=true`) on tasks that call Gemini APIs — a single fund can take 5+ minutes, batches can take hours. Use `ps aux \| grep scriptname` and `tail -N outputfile` to monitor progress instead.** |

### Signal misattribution (frontend text matching)

The web app's `signalFundTags.ts` matches signal text against fund names to show related signals on fund pages. This text-matching system can cause **cross-entity misattribution** if fund names share words with other entities.

**How it works**: `buildFundMentionEntries()` creates regex patterns from fund names:
1. **Full name pattern**: e.g., `"cherry bay capital"` — specific
2. **Cleaned name pattern**: strips legal suffixes (SGR, S.p.A., etc.)
3. **First-word short brand**: first word is used when it is ≥6 chars, not in `GENERIC_SHORT_BRANDS`, and maps to exactly one fund

**The bug class**: Long legal names with generic first words can still misattribute signals. Example: `"Sviluppo Imprese Centro Italia SGR"` can be matched by generic prose containing `sviluppo`.

**Prevention** (already enforced in code):
- Short brands are kept only when they are unambiguous (single-owner match)
- `GENERIC_SHORT_BRANDS` blocks generic English/Italian nouns from becoming standalone patterns (including `sviluppo`, `imprese`, `centro`, `italia`, `italiano`, `nazionale`)
- Inferred tags are sentence-local context-aware: speculative/candidate mentions (`among/fra/tra gli interessati`, `interested bidders/buyers`, `in the running`, `vying`) are not auto-tagged unless active-party evidence is present for that mention

**When adding a fund — check for this**:
1. If the fund name's **first word** is a common English/Italian noun or could appear in other entity names, verify it's in `GENERIC_SHORT_BRANDS` in `signalFundTags.ts`
2. After running the pipeline, check the fund's signals tab — look for signals that mention a **different entity** with a similar token
3. If misattributed signals appear, add the problematic word to `GENERIC_SHORT_BRANDS`

**Files**: `apps/web/src/lib/signalFundTags.ts` — `buildFundMentionEntries()` and `GENERIC_SHORT_BRANDS`

### During deployment

| Pitfall | Solution |
|---|---|
| `pnpm seed` overwrites curated db.json | Use `--force` flag only intentionally — seed has a safety guard |
| AIFI scraper sets wrong HQ for global funds | Cross-check `offices[]` after any AIFI merge |
| Fund doesn't appear on map | Run `pnpm worker:geocode && pnpm merge-aifi` to populate coordinates |
| Italian office has generic address like `Milan` | Agent must resolve to street-level via web lookup + Gemini API (no manual user research by default); if unresolved, explicitly report blocker and sources attempted |
| AI mentioned in UI | Never disclose AI in user-facing text — reference sources, not tools |
| AIFI creates duplicate fund under legal name | Add alias in `fund_aliases.json` mapping legal-name slug to canonical slug |

### Cost traps

> **Note**: Cost estimates are approximate. See `apps/worker/CLAUDE.md` for current API pricing and cost analysis.

| Action | Impact | Prevention |
|---|---|---|
| Deleting `signal_enrichment_progress.json` | Full re-enrichment (several dollars) | Never delete it |
| Running enricher repeatedly during debugging | Adds up fast | Edit `detected_signals_enriched.json` directly instead |
| Removing DeepL translation layer | Increases per-run cost | Keep DeepL as primary translator |
| Running LinkedIn scraper for testing | Wastes limited monthly runs | Never test — runs are capped. See `apps/worker/CLAUDE.md` for limits. |

---

## Reference: Manual Signal Creation

When adding signals manually (e.g., for newly added funds with historical Italy-relevant events), follow these rules carefully.

### Valid Signal Types

The **only** valid values for `signal_type` are defined in `SignalType` in `packages/shared/src/types.ts`:

| Signal Type | Description |
|---|---|
| `fundraise_announced` | Fund announces a new fundraise |
| `fundraise_closed` | Fund closes a fundraise |
| `fund_launch` | New fund vehicle launched |
| `deal_announced` | New investment/acquisition announced |
| `exit_announced` | Portfolio company sale/exit announced |
| `debt_financing` | Bonds, refinancings, credit facilities, mezzanine |
| `report` | Annual/sustainability/ESG reports |
| `partnership` | Strategic partnership or collaboration |
| `people_move` | Key hire, departure, or appointment |
| `job_posting` | Career/hiring signal |
| `portfolio_update` | News about existing portfolio companies |
| `website_change` | Website content change detected |
| `other` | Doesn't fit other categories |

> **WARNING**: `"exit"` is NOT a valid signal type — you must use `"exit_announced"`. This is the most common mistake when creating manual signals.

### Manual Signal Template

Add manual signals to **both** `data/derived/detected_signals_filtered.json` and `data/derived/detected_signals_enriched.json`.

```json
{
  "id": "manual-{fund-slug}-001",
  "fund_id": "",
  "fund_slug": "{fund-slug}",
  "signal_type": "deal_announced",
  "signal_types": ["deal_announced"],
  "title": "Clear, factual English title describing the event",
  "what_changed": "1-2 sentence description of what happened, with key details (amounts, companies, dates).",
  "source_url": "https://example.com/real-article-url",
  "source_name": "Reuters",
  "published_at": "2025-06-15T00:00:00.000Z",
  "observed_at": "2026-02-25T00:00:00.000Z",
  "created_at": "2026-02-25T00:00:00.000Z",
  "quality_score": 85,
  "italy_relevant": true,
  "enriched_summary": "",
  "extraction_source": "manual"
}
```

### Rules for Manual Signals

1. **Signal types**: Only use values from the `SignalType` enum above — NEVER `"exit"`, always `"exit_announced"`
2. **Source URLs**: Must be real, verifiable URLs from reputable sources (Reuters, FT, BeBeez, Il Sole 24 Ore, etc.)
3. **Quality score**: Set to `85` (above the 80 threshold) for verified manual signals
4. **IDs**: Use format `manual-{fund-slug}-NNN` (3-digit sequential)
5. **Both files**: Add to both `detected_signals_filtered.json` AND `detected_signals_enriched.json`
6. **enriched_summary**: Set to `""` for manual signals — the frontend will display the title
7. **Language**: Write title and what_changed in English
8. **italy_relevant**: Set to `true` for Italy-related events

---

## Quick Reference: Commands

| What | Command |
|---|---|
| Look up fund slug | `python3 -c "import json; [print(f['slug'], f['name']) for f in json.load(open('data/db.json'))['funds'] if 'TERM' in f.get('name','').lower()]"` |
| Test extractor loads | `cd apps/worker && python -c "from fundradar_worker.strategies.extractors.{slug} import *; print(EXTRACTORS)"` |
| Monitor single fund | `pnpm worker:monitor --slugs {slug}` |
| Full pipeline for fund | `pnpm pipeline --slugs {slug}` |
| Force re-extraction | `pnpm pipeline --slugs {slug} --force-extract` |
| Full mandatory new-fund workflow | `pnpm pipeline:new-fund-quality --slugs {slug}` |
| Full workflow + scoped missing-asset apply | `pnpm pipeline:new-fund-quality --slugs {slug} --apply-missing-assets` |
| Batch workflow for all new/outlier funds | `pnpm pipeline:new-fund-quality --auto-detect-new --apply-missing-assets` |
| Network preflight (DNS) | Use the snippet in §18.0.1 |
| Deterministic PR hard gate | `pnpm verify:new-fund-gate --base-ref <base_sha> --head-ref <head_sha>` |
| Filter + enrich only | `pnpm pipeline:signals` |
| Check portfolio output | `python3 -c "import json; d=json.load(open('data/derived/portfolio_items.json')); print(len(d.get('fund_portfolios',{}).get('{slug}',[])))"` |
| Check filtered/enriched parity for slug | `python3 -c "import json; slug='{slug}'; f=[s for s in json.load(open('data/derived/detected_signals_filtered.json')).get('signals',[]) if s.get('fund_slug')==slug]; e=[s for s in json.load(open('data/derived/detected_signals_enriched.json')).get('signals',[]) if s.get('fund_slug')==slug]; fi={s.get('id') for s in f}; ei={s.get('id') for s in e}; print('filtered',len(f),'enriched',len(e),'missing_in_enriched',len(fi-ei),'stale_in_enriched',len(ei-fi))"` |
| Check enrichment progress | `python3 -c "import json; d=json.load(open('data/derived/signal_enrichment_progress.json')); print(len(d.get('processed_ids',[])),'processed')"` |
| Generate fund description | `python3 scripts/generate-fund-descriptions-gemini.py --slugs {slug}` (from repo root) |
| Audit data quality | `pnpm audit:quality` |
| AIFI scrape + merge | `pnpm aifi:full` |
| Geocode addresses | `pnpm worker:geocode && pnpm merge-aifi` |
| URL coverage stats | `cd apps/worker && python -m fundradar_worker.url_generator` |
| Start dev server | `pnpm dev` |
| Build for production | `pnpm build` |
