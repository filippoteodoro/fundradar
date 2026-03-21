# AIFI Data

Data scraped from AIFI (Associazione Italiana del Private Equity, Venture Capital e Private Debt) - the Italian PE/VC industry association.

## Source

Website: https://www.aifi.it/
Data is scraped by `apps/worker/fundradar_worker/aifi_scraper.py`

## Directory Structure

### Category Directories
Each directory contains CSV files with fund names grouped by that category:

| Directory | Contents |
|-----------|----------|
| `Sector/` | Funds by industry focus (Healthcare, Tech, etc.) |
| `Geography/` | Funds by geographic focus (Italy, Europe, Global) |
| `Asset class/` | Fund types (Buyout, Growth, Venture, etc.) |
| `Investment focus/` | Investment stage preferences |
| `Average investment/` | Typical deal sizes |

### Key Files

| File | Purpose |
|------|---------|
| `all.csv` | Complete member list with all categories |
| `SOURCE.md` | Data source documentation |

### LinkedIn URL Files

| File | Purpose |
|------|---------|
| `monitor-urls-linkedin-aifi.md` | LinkedIn company URLs for AIFI members |
| `monitor-urls-linkedin-aifi.md.report.csv` | URL discovery results |
| `linkedin-search-fallbacks.md` | Manual fallback URLs |

### Debug/Reference Files

| File | Purpose |
|------|---------|
| `broken_funds.txt` | Funds with broken/missing URLs |
| `Investment Portfolio _ Carlyle.*` | Reference HTML snapshot |

Raw downloaded reference PDFs in this folder are local-only scratch material. Keep them untracked.

## CSV Format

All category CSVs have the same structure:
```
fund_name,website,linkedin_url,category_value
```

## Usage

The AIFI data feeds into:
1. `data/db.json` - Master fund database
2. `data/derived/aifi_members*.json` - Enriched member data
3. Monitor URL lists for website tracking

## Refresh Schedule

Run `poetry run python -m fundradar_worker.aifi_scraper` to refresh AIFI data.
Recommended: Monthly refresh to catch new members.
