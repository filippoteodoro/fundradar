# Fund Quality Score Optimization Workflow

## Quick Reference

**Scoring weights**: Portfolio (40%), Signals (25%), AIFI (20%), Profile (15%)
**Grade thresholds**: A>=80, B>=60, C>=40, D>=20, F<20
**Audit command**: `pnpm audit:quality`

Many remaining C-grade funds have signals=0 (25% weight = 0 pts). Signals cannot be fixed with data edits alone (need custom extractors). Focus on portfolio sectors and AIFI metadata.

---

## Two Optimization Levers (data-only, no code changes needed)

### Lever 1: Portfolio Sector Enrichment (+4 to +26 composite pts)

**How it works**: Adding sectors to portfolio companies with `sector: null` increases sector coverage from 0% toward 75%+, which adds +10 to portfolio score (+4 composite pts at 40% weight). Funds that also gain from the indirect effects (like Consilium gaining +26) see even bigger jumps.

**Process**:
1. Extract company names: `python3 -c "import json; data=json.load(open('data/derived/portfolio_items.json')); [print(f'{e[\"name\"]}: {e[\"sector\"]}') for e in data['fund_portfolios'].get('SLUG', [])]"`
2. Classify each company into one sector from the taxonomy
3. Add sector map to `scripts/enrich-sectors.ts`
4. Run: `cd scripts && npx tsx enrich-sectors.ts`
5. Verify: `pnpm audit:quality`

**Valid sectors** (use EXACTLY these strings):
Healthcare, Technology, Industrial, Consumer, Financial Services, Business Services, Energy, Infrastructure, Food & Beverage, Real Estate, Media & Telecom

**Sector map format** in `enrich-sectors.ts`:
```typescript
'fund-slug': {
    'lowercase company name': 'Sector',
    'another company': 'Sector',
},
```

**Critical rules**:
- The key must be the **exact** lowercase of the `name` field in portfolio_items.json
- Watch for special characters: accents (SESS\u00d9N), zero-width spaces, pipe suffixes ("Company | Fund Name")
- For pipe-suffixed names, add BOTH the clean name and the full pipe name as keys
- The script only overwrites `null` sectors - existing sectors are preserved
- Don't classify garbage entries (navigation text, person names, section headers)
- Fund slug must match the key in `portfolio_items.json` `fund_portfolios` (check `AIFI_NAME_OVERRIDES` - e.g. "BU" not "BU Italy")

### Lever 2: AIFI Metadata Enrichment (+4 to +12 composite pts)

**How it works**: Each missing AIFI field is worth 5-20 pts on the AIFI score (20% weight = 1-4 composite pts each).

**AIFI score breakdown** (100 pts total):
| Field | Points | Check |
|-------|--------|-------|
| `aum_eur` | 20 | > 0 |
| `num_portfolio_companies` | 15 | > 0 |
| `num_funds` | 10 | > 0 |
| `num_executives` | 10 | > 0 |
| `investment_min_eur` OR `max` | 10 | either > 0 |
| Both `min` AND `max` | +5 | both > 0 |
| `geographies[]` | 5 | length > 0 |
| `average_investment[]` | 5 | length > 0 |
| `asset_class[]` | 5 | length > 0 |
| Any contact (name/email/phone) | 5 | any non-empty |
| All 3 contacts | +5 | all non-empty |
| `num_sfdr_article_8` | 5 | typeof number |

**Note on SFDR:** Not all funds should have SFDR Article 8/9 funds. SFDR only applies to EU-marketed funds with ESG characteristics (regulation effective March 2021). Legitimately 0 for: non-EU funds, pre-2021 funds, funds without ESG focus. Use `0` for these cases rather than `null`.

**Process**:
1. Check current AIFI details in audit JSON: `python3 -c "import json; [print(f) for f in json.load(open('data/derived/fund_quality_audit.json'))['funds'] if f['slug']=='SLUG'][0]['details']['aifi']"`
2. Generate the AIFI refresh queue: `python3 scripts/aifi-refresh-queue.py`
3. Identify missing fields worth most points
4. Research values from fund website / AIFI source / public filings
5. Update `data/db.json` directly (use python to parse/write JSON safely)

**Where funds live**:
- Most funds: `data/db.json` (AIFI-scraped)
- Non-AIFI mega-funds: `data/db.json` with `data_source` indicating manual/Gemini
- Check both: `python3 -c "import json; db=json.load(open('data/db.json')); [print(f['slug'], f.get('aum_eur')) for f in db['funds'] if f['slug']=='SLUG']"`

---

## Prioritization: Which Funds to Optimize First

### Tier 1: C-grade funds with portfolio entries and null sectors (highest ROI)
These cross the C-to-B threshold with just sector enrichment:

| Fund | Score | Companies | Null Sectors |
|------|-------|-----------|-------------|
| tikehau-capital | 58 | 12 | 12 |
| siryo | 54 | 10 | 10 |
| key-capital | 44 | 8 | 8 |
| simest | 53 | 9 | 7 |
| zest-group | 54 | 5 | 5 |
| eurizon-capital-real-asset-sgr | 51 | 4 | 4 |

### Tier 2: C-grade funds scoring 57-59 (near B threshold)
These need only +1-3 pts from AIFI enrichment to cross 60:

Funds at 59: anthilia-sgr, aurora-growth-capital, avm-sgr, claris-ventures-sgr, igi-private-equity, l-b-capital-sgr, macquarie-mam, ring-capital, scientifica-vc

Funds at 58: clessidra-capital-credit-sgr, fiee-sgr, finint-investments-sgr, invitalia, oxy-capital, prana-ventures, rancilio-cube-sicaf, tikehau-capital

### Tier 3: Lower C-grade funds (more work, less likely to cross)
Funds scoring 50-56 need multiple improvements to reach B.

---

## Cost-Saving Rules for Sonnet

1. **NEVER web-search individual portfolio companies** - this is extremely credit-expensive
2. **Classify sectors from context**: fund description + company name is usually enough
   - VC fund investing in "SkinLabo" → Consumer (cosmetics brand name)
   - PE fund with "Fonderia Boccacci" → Industrial (fonderia = foundry)
   - Impact fund with "Areamedical24 Societa Benefit" → Healthcare
3. **Only web-search when genuinely ambiguous** (e.g., "ACT" could be anything)
4. **Batch searches**: if you must search, search the fund name + "portfolio" once, not each company
5. **Use the audit JSON** to check exact missing fields before researching - don't research fields that already exist
6. **Process multiple funds per message** - don't launch separate agents per fund
7. **ALWAYS cite specific URLs from search results** - use the actual page URLs returned by WebSearch, NOT generic homepage links (e.g., "https://www.apollo.com/insights-news/pressreleases/2023/04/..." not "https://www.apollo.com/")

---

## Garbage Data Patterns (DO NOT classify these)

Portfolio entries that are NOT real companies:
- Navigation labels: "Portfolio", "Il Gruppo", "Private Equity", "Contatti", "Immobiliare"
- Section headers: "Partecipazioni Industriali", "Social Impact"
- Person names instead of companies (team page scrape artifacts)
- Fund's own name appearing as portfolio entry
- Generic UI text: "What", "Who", "How", "Key Numbers", "La prospettiva di..."
- Entries with null sector AND null status AND null website AND generic name

---

## Verification Checklist

After each batch of changes:
1. Run `cd scripts && npx tsx enrich-sectors.ts` (for sector changes)
2. Run `pnpm audit:quality`
3. Check the target funds improved: `python3 -c "import json; d=json.load(open('data/derived/fund_quality_audit.json')); [print(f['slug'], f['compositeScore'], f['grade']) for f in d['funds'] if f['slug'] in ['SLUG1','SLUG2']]"`
4. Verify no regressions in already-optimized funds

## Files Reference

| File | Purpose |
|------|---------|
| `scripts/enrich-sectors.ts` | Sector maps, run to apply |
| `data/derived/portfolio_items.json` | Portfolio data (sectors written here) |
| `data/db.json` | Fund metadata (AIFI fields) |
| `data/db.json` | Non-AIFI mega-fund data (flagged via `data_source`) |
| `data/derived/fund_quality_audit.json` | Latest audit results |
| `apps/web/src/lib/fundQuality.ts` | Scoring logic (read-only reference) |
