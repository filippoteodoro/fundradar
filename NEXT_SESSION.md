# NEXT_SESSION

Site is live & current (June 2026 refresh). The iCloud→local move fallout and the deferred
signal-quality items from that run are resolved (see git log). Only these follow-ups remain —
all need a user decision, live investigation, or credentials, not a clean code fix.

## Evaluate 2 possibly-genuine new PE/VC funds
The gap detector flagged these; they were NOT excluded and will keep alerting until decided:
- **Kryalos SGR** — real-estate PE/RE asset manager. Borderline (RE focus). Decide in (add fund + extractor) or out (`excluded_entities`).
- **Soprarno SGR** (now L&B Capital, ex-Banca Ifigest) — small PE. Verify it's PE/VC, then add or exclude.

## 11 persistent URL failures — verify live before editing extractor URLs
Worker-doc rule: do NOT null URLs that are merely blocked/down.
- 403 bot-block (likely transient, leave): `apax.com` (3 paths), `oakleycapital.com` (3 paths).
- 404 persistent (investigate): `aimpact.org/portafoglio`+`/en/news` (13×, was a *temporary* 503 — likely restructured),
  `triton-partners.com/media/news/`, `cherrybaycapital.com/cherries/`+`/about/team/`.

## Translation: single-DeepL-key gap (no fallback)
Only `DEEPL_API_KEY` is configured; ~6 fields/run go untranslated and leak Italian into the filter (false-friend
mis-typing, e.g. "sale"=rises). Add `DEEPL_API_KEY_2` or an Azure Translator key to restore the documented fallback chain.

## `data/pem/*.pdf` source PDFs lost in the move
`pem_deals.json` (derived) is committed & intact, so nothing is user-facing. Only needed to RE-ingest PEM.
Locate the original PDFs (off-machine backup?) or accept that PEM can't be re-ingested.

## Optional / watch
- `enrich_portfolio` + `enrich_portfolio_final` hit the pipeline step timeout (the cause of the now-cleared 53-entry
  backlog). Bump the step timeout for those two Gemini steps in `pipeline.py` if the backlog recurs.
- rss-230/193 stock-commentary demotions are patched but trip `_matches_exit` guards at filter time, so similar
  *future* market-commentary that also names a transaction may slip — watch the audit.
- Fundradar-root `AGENTS.md` (untracked, your in-flight CLAUDE.md→AGENTS.md migration) still cites the old iCloud
  Tier-1 path; update when that migration lands. (Worker `CLAUDE.md` + `runbook.md` already corrected.)
