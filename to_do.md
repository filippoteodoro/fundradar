# to_do

Open backlog for contributors. Each item is independent. Open an issue before large changes.

## Hide zero-Italy funds on the website
`data/derived/gemini_fund_asset_zero_italy_verified.json` lists funds with zero Italian assets, but `getAllFunds()`
in `apps/web/src/lib/data.ts` still returns them (for example `canova-sgr`). The spec is in `apps/web/CLAUDE.md`.

## Make the top-AUM signal backfill survive a full filter run
`scripts/backfill_top_aum_signals.py` writes only to the filtered and enriched signal files, so a full filter run
can drop those signals. Feed them through the raw signal input instead.

## Decide on 2 fund candidates
The gap detector flags these. Add each one (fund entry + extractor) or exclude it (`db.json["excluded_entities"]`):
- **Kryalos SGR**: real-estate focus. Borderline for the PE/VC scope.
- **Soprarno SGR** (now L&B Capital, ex-Banca Ifigest): small PE firm. Verify it is PE/VC first.

## Persistent URL failures
Verify each URL live before you edit an extractor. Do not remove a URL that is only blocked or down.
- 403 bot-block, probably transient: `apax.com` (3 paths), `oakleycapital.com` (3 paths).
- 404, investigate: `aimpact.org/portafoglio` and `/en/news`, `triton-partners.com/media/news/`,
  `cherrybaycapital.com/cherries/` and `/about/team/`.

## Translation fallback
With only one translation key, fields that fail translation stay in Italian and can cause wrong signal types
(for example "sale" means "rises" in Italian). Set a second key (`DEEPL_API_KEY_2` or `AZURE_TRANSLATOR_KEY`)
to use the fallback chain in `apps/worker/fundradar_worker/translator.py`.

## PEM re-ingest
The PEM source PDFs are not in the repo. `data/derived/pem_deals.json` is committed and complete.
To re-ingest, put the PEM PDFs in `data/pem/` and run `pnpm worker:ingest`.

## Watch
- `enrich_portfolio` and `enrich_portfolio_final` can hit the pipeline step timeout. If a backlog builds up,
  increase the step timeout for these two steps in `apps/worker/fundradar_worker/pipeline.py`.
- Market-commentary articles that also name a transaction can pass the `_matches_exit` guard in `apps/worker/scripts/signal_corrections.py`.
  Check the filter audit output for this pattern.
