# NEXT_SESSION

Goal: clean up the fallout from the iCloud→local move and the deferred signal-quality items
surfaced by the June 2026 pipeline refresh (commit `deaf68a`). Site is live & current; these are follow-ups.

## HIGH — missing gitignored data (iCloud→local move dropped them)
Repo now lives at `/Users/filippoteodoro/Code/Fundradar` (off iCloud). The move was a clone/partial
copy, so gitignored dirs were left behind. No backup found anywhere on disk (Trash empty, TM unmounted).
- `data/derived/linkedin/raw/` — **GONE, irreplaceable**. **Decision: do NOT re-scrape** — LinkedIn is a
  yearly-only manual job (cadence now hard-documented in `batch_scraper.py`, worker CLAUDE.md, linkedin-scraping.md).
  Committed `linkedin/fund_people_stats.json` + `team_items.json` are the live site source and are intact. Loss accepted.
- `data/pem/*.pdf` — GONE. `pem_deals.json` committed & present. Only needed to re-ingest PEM. Locate PDFs or accept.
- `data/models/` — was missing; **already regenerated** via `train_signal_classifier.py` (free, no action).

## MED — db.json sector_tags clobbered every pipeline run
`normalize_sectors` rewrites curated fund-level `sector_tags` in `data/db.json` (broad diff, drops curated
values e.g. Ardian → "Telecommunications"). Restored from git this run per the worker-doc rule. It will
recur every run. Fix: make the step not overwrite curated `db.json` sector_tags (or consciously accept its output).

## MED — ~6 news-digest/commentary signals mis-tagged as deal/exit
Should be `other`. Fix systemically in `signal_corrections.py::apply_universal_demotions()` + a test, then
refilter + re-enrich. IDs: `rss-signal-00119` (carlyle, "This week's executive shuffles"),
`rss-signal-00230` (apollo, "Trading Floor:"), `rss-signal-00062`/`00193` (merito-sgr, Mastercard/Nexi commentary).

## LOW — ~3 untranslated Italian titles slipped DeepL
`rss-signal-00101` (blackstone), `rss-signal-00274` (the-equity-club), `web-signal-00046` (fondo-italiano).
Free fix: set English title + `title_original` directly in `detected_signals_{filtered,enriched}.json` (Pitfall #27).

## LOW — 53 portfolio entries await Gemini sector enrichment (ROOT CAUSE: step timeout)
Telegram showed `enrich_portfolio` + `enrich_portfolio_final` both hit `timeout (exit -1)` — that's why 53
entries remain (mostly sector-only: portobello-capital 16, trilantic-europe 7, …). The pipeline marks these
steps optional so it still completed. Clear by running standalone (no step timeout):
`python apps/worker/scripts/enrich_portfolio_gemini_full.py --pipeline` (small Gemini cost). Or bump the
step timeout for the two Gemini portfolio steps in `pipeline.py`. Not user-blocking.

## LOW — 11 persistent URL failures (extractor maintenance)
Mostly bot-blocking (403) or moved pages (404), from the June log:
- 404 (persistent): `aimpact.org/portafoglio` + `/en/news` (13×), `triton-partners.com/media/news/`, `cherrybaycapital.com/cherries/` + `/about/team/`.
  aimpact was previously documented as a *temporary* 503 — 13× 404 suggests the site restructured; verify live before editing URLs.
- 403 (bot-blocked, likely transient): `apax.com` (3 paths), `oakleycapital.com` (3 paths). Per worker-doc rule, do NOT null these — they're blocked, not gone.

## LOW — 16 "unknown fund" gap-detector alerts (mostly NOT new funds)
Per the PE/VC-only scope rule, most are noise — triage before adding anything:
- **Fund vehicles of tracked managers (alias, don't add):** Blackstone PE Fund, Armònia Italy Fund II, ARMES/SME Development Fund (FVS), NPL Nextalia (Raffaello), Clessidra PE.
- **Name-variants of existing db.json funds (alias):** Anthilia Capital Partners (=anthilia-sgr), Finanziaria Internazionale Investments (=finint-investments-sgr), Capital Alternative Funds (=dea-capital-alternative-funds-sgr).
- **Excluded entity types (add to db.json `excluded_entities`):** Generali Real Estate (asset mgr), Arca Fondi (asset mgr), Hedge Invest (hedge fund), Credem PE (bank-affiliated).
- **Possibly genuine new PE/VC — evaluate:** Kryalos (real estate PE), Consilium, Soprarno/L&B Capital.
Adding aliases/exclusions stops the repeat alerts (30-day dedup window in `unknown_fund_gaps.json`).

## LOW — 6 translation fields unresolved (Telegram alert)
DeepL left 6 fields untranslated (only `DEEPL_API_KEY` configured; no `DEEPL_API_KEY_2`/Azure fallback).
Overlaps the ~3 Italian titles above. Either add an Azure fallback key, or patch titles directly (free).

## NOTE — stale doc paths
Worker `CLAUDE.md` still cites the old iCloud Tier-1 path (`~/Library/Mobile Documents/…/Fundradar/`).
Repo is now at `~/Code/Fundradar`. Update when the CLAUDE.md/AGENTS.md migration (already in flight) lands.
