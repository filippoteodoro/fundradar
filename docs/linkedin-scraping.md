# LinkedIn Scraping

This document owns the LinkedIn people-data workflow. The code is in `apps/worker/fundradar_worker/linkedin/`.

## What it produces

| File | Committed | Contents |
|------|-----------|----------|
| `data/derived/linkedin/fund_people_stats.json` | Yes | Per-fund team statistics. The fund page team charts read it through `getTeamAnalyticsForFund()`. |
| `data/derived/linkedin/fund_linkedin_urls.json` | Yes | Fund LinkedIn company URLs. `data.ts` merges them into each fund at load time. |
| `data/derived/linkedin/manual_profiles.json` | Yes | Hand-curated profile links for funds that the batch scraper skips. |
| `data/derived/linkedin/raw/` | No (gitignored) | Raw scraped profiles. A fresh clone does not have this directory. |

## Cadence rule

LinkedIn scraping is not part of `pnpm pipeline`. Run it only on explicit request, at most once per year per fund.

- Every run spends paid Apify credits.
- The HarvestAPI actor (`--rich`) limits free Apify plans to 10 runs per month. A run past that limit returns 0 profiles and still costs credits.
- Do not re-scrape to refresh data, to fix one fund, or to fill a gap. The committed `fund_people_stats.json` stays valid between scrapes.
- A missing `raw/` directory is not a reason to re-scrape.

## Commands

All commands run from `apps/worker` with the virtual environment active. `APIFY_API_TOKEN` must be set.

```bash
# Batch scrape (paid). Default actor: apimaestro (headline data).
python -m fundradar_worker.linkedin.batch_scraper --max-employees 25 --max-cost 2.50 --delay 180

# Same, with the HarvestAPI actor (full experience and education, 10 runs/month on free plans)
python -m fundradar_worker.linkedin.batch_scraper --rich --max-employees 25 --max-cost 2.50 --delay 180

# Rebuild stats from manual_profiles.json, title-based classification (free)
python -m fundradar_worker.linkedin.process_manual_profiles --basic

# Enrich manual profiles through Apify first (paid)
python -m fundradar_worker.linkedin.process_manual_profiles --enrich
```

Keep `--delay 180` for batch runs. LinkedIn rate-limits rapid runs per hour, even inside the Apify run allowance.

If a run returns 0 profiles, read the Apify run log. A "free user run limit" message means the monthly limit is spent. Otherwise, wait 1–2 hours for the LinkedIn rate limit to reset.

## Which funds get scraped

- `MEGA_FUNDS_TO_SKIP` and `FOREIGN_FUNDS_TO_SKIP` in `batch_scraper.py` list global funds that the batch scraper skips.
- `manual_profiles.json` is the source of truth for funds covered by hand-curated profiles. Do not infer that coverage from the skip sets.
- Scrape Italian domestic and mid-size funds first. Their teams are small, so 25 profiles give near-full coverage.

## Raw data protection

`raw/*_employees.json` (HarvestAPI) and `raw/*_enriched_profiles.json` (Apify profile scraper) hold full profiles: education, experience and skills. Only a paid re-scrape can replace them.

- Parse HarvestAPI files with `harvestapi_to_profile()` in `people_stats.py`. Do not reduce them to single-experience profiles.
- Scripts that read `raw/` and write `fund_people_stats.json` are safe.
- Never run a script that writes to `raw/` or `manual_profiles.json` without explicit approval from the person who pays for Apify.

## Website copy rule

Never show the word "LinkedIn" in user-facing text. Use "public profiles". Icon links are allowed.
