# Fund Page Credibility Audit — Sonnet Prompt

> Copy-paste this entire prompt into a new Claude session to fix fund portfolio data.

---

## Your Task

You are fixing portfolio data for Italian PE/VC funds. The fund pages must look credible to industry experts. The main problem: many portfolio entries have `status: null`, which the web app defaults to "current" — showing long-exited companies as active investments.

You will work in batches of 3-5 funds, starting with Tier 1 (most critical).

## Files You Need

1. **`data/derived/fund_page_audit.json`** — the audit diagnostic. Read this first. It contains:
   - `summary` — tier counts, total null-status entries
   - `funds[]` — sorted by tier then AUM. Each fund has: `slug`, `tier`, `portfolio_entries`, `pem_deals`, `red_flags`, `suggested_actions`

2. **`data/derived/portfolio_items.json`** — the file you will edit. Structure:
   ```json
   {
     "fund_portfolios": {
       "[slug]": [
         {"name": "...", "status": "current"|"exited"|null, "sector": "...", ...}
       ]
     }
   }
   ```

3. **`docs/fund-page-audit-workflow.md`** — reference for status rules and PEM decoder.

## Step-by-Step Process

### Step 1: Pick the Next Batch

Read `data/derived/fund_page_audit.json`. Find the first 3-5 funds with `tier: 1` that haven't been fixed yet. If all Tier 1 are done, move to Tier 2.

How to tell if a fund is already fixed: check its entry in `portfolio_items.json` — if entries still have `"status": null`, it hasn't been fixed.

### Step 2: Research Each Fund

For each fund in the batch:

1. **Read its audit entry** from `fund_page_audit.json` — note `red_flags`, `portfolio_entries`, `pem_deals`
2. **WebSearch**: `"{fund name}" portfolio companies Italy 2024` — **ONE search per fund**, not per company
3. **Cross-reference**:
   - Match PEM deal `target_company` names against what you find on the fund's website
   - Determine which companies are still in the portfolio vs. exited
4. **Note findings** before making changes

### Step 3: Update portfolio_items.json

For each fund, edit `data/derived/portfolio_items.json`:

**Fix null-status entries:**
- Set `"status": "exited"` for confirmed exits (keep the entry, just fix status)
- Set `"status": "current"` for confirmed current investments
- If uncertain but PEM deal is from before 2015: set `"exited"`
- If uncertain but PEM deal is from 2018+: leave as `"current"` (typical PE hold is 5-7 years)

**Add missing current investments:**
- If the fund's website shows Italian portfolio companies not in our data, add them
- Use this exact format:
  ```json
  {
    "name": "Company Name",
    "sector": "Sector / Sub-sector",
    "status": "current",
    "confidence": 0.9,
    "website": "https://company-website.com",
    "description": "Brief description of the company.",
    "detail_page_url": "https://fund.com/portfolio/company",
    "headquarters": "City, Italy",
    "investment_date": "YYYY-01-01"
  }
  ```
- Only add companies you can verify from the fund's official website or press releases
- Prefer 5 verified entries over 20 uncertain ones

**Remove garbage entries:**
- Delete entries that are navigation text, section headers, or scrape artifacts
- Examples: "Portfolio", "Our Investments", "Back to top", "Soluzioni di investimento"

### Step 4: Verify

After each batch, run:
```bash
pnpm audit:quality
```
This checks data completeness scores. Verify the fixed funds improved.

## Classification Rules

### Status Decision Tree

```
Is the company on the fund's current portfolio page?
  YES → status: "current"
  NO  → Does PEM data show Exit/IPO/Trade Sale in deal_origination?
          YES → status: "exited"
          NO  → Is the PEM deal from before 2015?
                  YES → status: "exited" (>10 year hold is rare)
                  NO  → Is the PEM deal from 2015-2019?
                          → status: "exited" unless evidence of current hold
                        Is the PEM deal from 2020+?
                          → status: "current" (within typical hold period)
```

### PEM deal_origination Decoder

| deal_origination value | What it means | Status implication |
|------------------------|---------------|-------------------|
| "Buy Out" | Fund acquired the company | Entry investment — likely current if recent |
| "Secondary Buy Out" | Fund bought from another PE firm | Entry investment — the fund BOUGHT it |
| "Expansion" | Growth investment | Entry investment — likely current |
| "Replacement" | Replacement capital | Entry investment |
| "Turnaround" | Restructuring investment | Entry investment |
| "Exit" | Fund sold the company | **Exited** |
| "IPO" | Company went public | **Exited** |
| "Trade Sale" | Sold to strategic buyer | **Exited** |
| "Other" | Unclassified | Check year — if old, likely exited |

**Key rule**: "Secondary Buy Out" means the fund BOUGHT the company. It does NOT mean the fund sold it. The "secondary" refers to it being the second (or later) PE owner.

### What NOT to Do

- Do NOT search for each company individually — one search per fund
- Do NOT add entries from non-Italian operations unless the fund is specifically tracked for Italy
- Do NOT use generic homepage URLs as `detail_page_url` — use the specific portfolio page or leave null
- Do NOT guess sectors or descriptions — use what the fund's website says, or leave null
- Do NOT change entries that already have a correct status ("current" or "exited")
- Do NOT remove entries just because you can't find them — they may be correct; only remove obvious garbage

## Example: Good Fix

**Before** (Advent International):
```json
{
  "name": "Venere",
  "status": null,
  "sector": null,
  "investment_date": null
}
```

**After** (found via search: Venere.com was sold to Expedia in 2012):
```json
{
  "name": "Venere",
  "status": "exited",
  "sector": "Technology / Online Travel",
  "investment_date": null
}
```

## Example: Bad Fix

```json
// BAD: Guessing without evidence
{"name": "Some Company", "status": "current", "sector": "Tech"}

// BAD: Removing an entry because you can't find it
// (it might be a small company not in search results)

// BAD: Adding a company from the fund's US/global portfolio
// (we only track Italian investments)
```

## Batch Tracking

After completing a batch, note which funds you fixed so the next session can continue where you left off. The audit JSON won't change until re-run, but `portfolio_items.json` will reflect your fixes.

To re-run the diagnostic after fixes:
```bash
python3 scripts/audit-fund-pages.py
```
