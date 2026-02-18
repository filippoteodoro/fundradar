# Fund Page Audit — Workflow Reference

## Overview

Fund pages must look credible to industry experts. The audit has two phases:

1. **Phase 1 (DONE)**: Null-status cleanup — fixed a large backlog of entries where exited companies showed as "current"
2. **Phase 2 (ACTIVE)**: Expert credibility review — ensuring fund pages show the right companies with complete data

### Phase 2: The Completeness Problem

The null-status fix was necessary but not sufficient. Many fund pages still lack credibility because:
- **Some mega-funds show too few companies** — pages can appear incomplete despite broad investment activity
- **Many entries are missing descriptions** — entries appear as bare names without context
- **Many entries are missing sectors** — no industry classification
- **Some funds still score low on credibility** — these should be prioritized for remediation

Use `docs/sonnet-fund-enrichment-prompt.md` for the Phase 2 enrichment workflow.

## Phase 1: The Null-Status Problem (COMPLETED)

## The Null-Status Problem

In `apps/web/src/lib/data.ts` (line 1139):

```typescript
status: c.status || ('current' as const),
```

When `portfolio_items.json` has `"status": null`, the web app displays the company as a current investment. This means exited companies (some from 10+ years ago) appear as active portfolio holdings.

**The fix is in the data, not the code.** Each null-status entry in `portfolio_items.json` needs its status set to `"current"` or `"exited"` based on research.

## Running the Audit

### 1. Generate the Diagnostic

```bash
python3 scripts/audit-fund-pages.py
```

This reads 5 JSON files and outputs:
- `data/derived/fund_page_audit.json` — full audit data
- Console summary with tier-sorted fund list

### 1.1 Generate the PEM Status Queue

```bash
python3 scripts/audit-pem-status.py
```

This produces:
- `data/derived/pem_status_audit.json` — PEM deals that lack verified status and need review

### 1.2 Generate the Asset Status Audit

```bash
python3 scripts/audit-asset-status.py
```

This produces:
- `data/derived/asset_status_audit.json` — all assets needing evidence to resolve status

### 2. Interpret Tiers

| Tier | Criteria | Risk |
|------|----------|------|
| **1** | AUM > €5B AND (current < 10 OR null_status > 5) | Major credibility risk — these are well-known funds |
| **2** | null_status > 3 OR (PEM deals > 3 AND current < 3) | Data accuracy risk |
| **3** | current < 5 AND PEM deals > 0 | Incomplete picture |
| None | Funds with reasonable data | Low priority |

### 3. Fix Funds in Batches

Use the Sonnet prompt (`docs/sonnet-fund-page-audit-prompt.md`) to fix 3-5 funds per batch, starting with Tier 1.

### 4. Verify After Each Batch

```bash
# Re-run the diagnostic to see updated counts
python3 scripts/audit-fund-pages.py

# Check fund quality scores
pnpm audit:quality
```

## Red Flag Reference

| Flag | Meaning | Action |
|------|---------|--------|
| `ALL_NULL_STATUS` | Every entry has `status: null` | Research all entries, set current/exited |
| `MOSTLY_NULL_STATUS` | >50% of entries have null status | Same as above for null entries |
| `MAJOR_FUND_FEW_ENTRIES` | €5B+ AUM but <10 entries | Add current investments from fund website |
| `PEM_EXIT_MISMATCH` | Entry shown as current but PEM suggests exit | Verify and set `status: "exited"` |
| `NO_CURRENT_PORTFOLIO` | Has PEM deals but 0 current entries | Add current investments from fund website |
| `GARBAGE_ENTRIES` | Navigation text or scrape artifacts | Delete from `portfolio_items.json` |
| `STALE_DATA` | Pre-2015 investment dates, not marked exited | Research and likely set `status: "exited"` |

## PEM deal_origination Decoder

Understanding PEM deal types is critical for determining exit status.

### Entry Investments (the fund BOUGHT)

| Value | Meaning |
|-------|---------|
| Buy Out | Majority acquisition |
| Secondary Buy Out | Bought from another PE fund |
| Expansion | Growth capital injection |
| Replacement | Replacement of existing investors |
| Turnaround | Restructuring investment |
| Infrastructure | Infrastructure asset acquisition |

### Exit Events (the fund SOLD)

| Value | Meaning |
|-------|---------|
| Exit | Generic exit |
| IPO | Listed on stock exchange |
| Trade Sale | Sold to strategic/corporate buyer |

### Ambiguous

| Value | Meaning |
|-------|---------|
| Other | Unclassified — use year as guide |

**Common mistake**: "Secondary Buy Out" means the fund **bought** the company from another PE firm. It does NOT mean the fund exited.

## Status Classification Rules

### By PEM Year

| PEM Year | Default Status | Rationale |
|----------|---------------|-----------|
| Before 2015 | `"exited"` | >10 year hold is extremely rare |
| 2015–2019 | `"exited"` | >6 year hold is uncommon |
| 2020–2022 | Uncertain | Check fund website |
| 2023–2024 | `"current"` | Within typical 5-7 year hold |

These defaults are overridden by direct evidence (fund website, press releases).

### Evidence Priority

1. **Fund website** — if the company is on the current portfolio page, it's `"current"`
2. **Press releases** — "exits", "IPO", "sale" announcements
3. **PEM deal_origination** — Exit/IPO/Trade Sale = `"exited"`
4. **PEM year** — use the year-based defaults above

## Files Reference

| File | Role | Modified By |
|------|------|-------------|
| `data/derived/portfolio_items.json` | Portfolio data — **you edit this** | Manual + worker |
| `data/derived/pem_deals.json` | PEM deal history | `pnpm worker:ingest` |
| `data/db.json` | Fund database | `pnpm merge-aifi` |
| `data/derived/fund_aliases.json` | Slug aliases | Manual |
| `data/derived/fund_page_audit.json` | Audit output | `python3 scripts/audit-fund-pages.py` |
| `data/derived/pem_status_audit.json` | PEM status review queue | `python3 scripts/audit-pem-status.py` |

## Portfolio Entry Format

When adding new entries to `portfolio_items.json`:

```json
{
  "name": "Company Name",
  "sector": "Sector / Sub-sector",
  "status": "current",
  "confidence": 0.9,
  "website": "https://company-website.com",
  "description": "Brief description of the company.",
  "detail_page_url": "https://fund.com/portfolio/company-name",
  "headquarters": "City, Italy",
  "investment_date": "YYYY-01-01"
}
```

**Rules:**
- `name` — use the brand name as shown on the fund's portfolio page
- `sector` — use the sector label from the fund website, or null if unknown
- `status` — always set explicitly: `"current"` or `"exited"`, never null
- `confidence` — 0.9 for entries verified from fund website/press releases
- `website` — company's own website, not the fund page
- `detail_page_url` — the fund's portfolio page for this specific company, or null
- `headquarters` — "City, Italy" format. Only Italian operations
- `investment_date` — use `YYYY-01-01` when only the year is known, null if unknown

## Typical Workflow Session

### Phase 2 Enrichment (current)

1. Run `python3 scripts/audit-fund-pages.py`
2. Look at "LOWEST CREDIBILITY" section — these are your targets
3. Use `docs/sonnet-fund-enrichment-prompt.md` in a Sonnet session
4. Work through 3-5 funds per batch, starting with lowest credibility scores
5. Re-run audit to verify credibility scores improved
6. Run `pnpm audit:quality` to check overall quality

### Phase 1 Status Cleanup (completed)

1. Run `python3 scripts/audit-fund-pages.py`
2. Open `data/derived/fund_page_audit.json`
3. Pick 3-5 Tier 1 funds
4. For each fund:
   - Check audit entry for red flags and PEM deals
   - Search: `"{fund name}" portfolio companies Italy`
   - Visit fund website portfolio page if available
   - Update entries in `portfolio_items.json`
5. Re-run audit to verify tier counts decreased
6. Run `pnpm audit:quality` to check quality scores
7. Repeat with next batch
