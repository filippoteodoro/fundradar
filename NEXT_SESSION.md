# NEXT_SESSION

Goal: clean up the fallout from the iCloud→local move and the deferred signal-quality items
surfaced by the June 2026 pipeline refresh (commit `deaf68a`). Site is live & current; these are follow-ups.

## HIGH — missing gitignored data (iCloud→local move dropped them)
Repo now lives at `/Users/filippoteodoro/Code/Fundradar` (off iCloud). The move was a clone/partial
copy, so gitignored dirs were left behind. No backup found anywhere on disk (Trash empty, TM unmounted).
- `data/derived/linkedin/raw/` — **GONE, irreplaceable**. Derived stats (`linkedin/fund_people_stats.json`,
  `team_items.json`) are committed & present, so the site is fine. Re-deriving/incremental LinkedIn needs
  a re-scrape (Apify $). Decide: accept loss, or re-scrape top funds next monthly window.
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

## LOW — 53 portfolio entries await Gemini sector enrichment (self-healing backlog)
Run `python apps/worker/scripts/enrich_portfolio_gemini_full.py --pipeline` to clear, or let it clear over runs.
Mostly sector-only (portobello-capital 16, trilantic-europe 7, …). Not user-blocking.

## NOTE — stale doc paths
Worker `CLAUDE.md` still cites the old iCloud Tier-1 path (`~/Library/Mobile Documents/…/Fundradar/`).
Repo is now at `~/Code/Fundradar`. Update when the CLAUDE.md/AGENTS.md migration (already in flight) lands.
