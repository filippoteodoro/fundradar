# Prompt for Claude Sonnet: Fund Quality Score Optimization

Copy this prompt to start a Sonnet session:

---

Read `docs/fund-quality-optimization-workflow.md` for the full workflow reference. Then optimize fund quality scores following these steps:

## Task: Sector Enrichment for C-Grade Funds

### Step 1: Identify targets
Run this to find C-grade funds with null sectors in portfolio:
```bash
python3 -c "
import json
with open('data/derived/fund_quality_audit.json') as f:
    audit = json.load(f)
with open('data/derived/portfolio_items.json') as f2:
    p = json.load(f2)
for f in audit['funds']:
    if f['grade'] == 'C':
        slug = f['slug']
        entries = p['fund_portfolios'].get(slug, [])
        null_sectors = sum(1 for e in entries if e.get('sector') is None)
        if null_sectors > 0:
            print(f'{slug}: score={f[\"compositeScore\"]} companies={len(entries)} null_sectors={null_sectors}')
"
```

### Step 2: For each target fund, extract company names
```bash
python3 -c "
import json
data = json.load(open('data/derived/portfolio_items.json'))
for e in data['fund_portfolios'].get('FUND_SLUG', []):
    if e['sector'] is None:
        print(repr(e['name']))
"
```

### Step 3: Classify sectors WITHOUT web searching
Use this taxonomy EXACTLY: Healthcare, Technology, Industrial, Consumer, Financial Services, Business Services, Energy, Infrastructure, Food & Beverage, Real Estate, Media & Telecom

Classify from name + fund context. Italian naming hints:
- "Fonderia" = foundry → Industrial
- "Alimentari/Cibo" = food → Food & Beverage
- "Farmacia/Pharma/Medical" = pharma → Healthcare
- "Immobiliare" = real estate → Real Estate
- "Assicurazioni" = insurance → Financial Services
- Fashion/luxury brands → Consumer
- "S.p.A./S.r.l." suffixes are just legal forms, ignore them
- "Societa Benefit" = B-corp status, classify by actual business

Only web-search if genuinely ambiguous (acronyms, generic names).

### Step 4: Add to enrich-sectors.ts
Read `scripts/enrich-sectors.ts`, add new sector maps after existing ones. Use lowercase company names as keys.

### Step 5: Run and verify
```bash
cd scripts && npx tsx enrich-sectors.ts
```
Then:
```bash
pnpm audit:quality
```

### Step 6: AIFI enrichment for funds scoring 57-59
For funds that are 1-3 points from B grade, check their AIFI details:
```bash
python3 -c "
import json
d = json.load(open('data/derived/fund_quality_audit.json'))
for f in d['funds']:
    if f['grade'] == 'C' and f['compositeScore'] >= 57:
        missing = [line for line in f['details']['aifi'] if line.strip().startswith('0')]
        if missing:
            print(f'{f[\"slug\"]} ({f[\"compositeScore\"]}): {missing}')
"
```
Then update db.json with missing fields (geographies, asset_class, investment range, etc.) using python to safely edit JSON.

## CRITICAL: Cost Control Rules
- DO NOT use WebSearch for individual company sector classification
- DO NOT launch background agents for research
- Classify 90%+ of companies from name + fund context alone
- Process 3-5 funds per iteration, not one at a time
- Read the audit JSON to check what's missing BEFORE researching anything
- When using WebSearch, ALWAYS cite the specific page URLs from search results, NOT generic homepage links (e.g., use "https://www.apollo.com/insights-news/pressreleases/2023/04/apollo-fund-portfolio..." not "https://www.apollo.com/")

## Target
- Move as many C-grade funds to B (score >= 60) as possible
- Current state: review `fund_quality_audit.json` for the latest C-grade backlog
- Focus on Tier 1 (have portfolio entries with null sectors) and Tier 2 (score 57-59, near threshold)

---
