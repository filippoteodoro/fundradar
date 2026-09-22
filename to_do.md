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

## Remove the duplicate HTML copy (~50% of snapshot storage)
`SnapshotStore.store()` in `apps/worker/fundradar_worker/fetcher.py` writes each page twice: once to `data/derived/blobs/`
(content-addressed) and once to the legacy `data/derived/snapshots_html/`. Change detection uses `content_hash`, not an
HTML diff, so the legacy copy has no function. Remove the legacy write and its read fallback, then delete the directory.
Keep the blobs: `--force-extract` on a 304 page reads the previous blob. Consider keeping only the latest blob per URL.

## Product ideas
None of these exist. Each one must keep the rules in `docs/reliability-contract.md` (source-cited, no predictions).
- **Weekly summary**: an LLM summary of the last 7 days of signals, plus headline stats on the home page
  (for example, the sector with the most activity). Each claim in the summary must link to its source signal.
- **Split multi-strategy managers by strategy**: for example Blackstone PE vs Tactical Opportunities, or the large-cap
  and mid-cap funds of Hg and Astorg. Assets that one strategy ignores can suit the other (minority, structured
  equity, FIG, smaller tickets). Today `CompanyInvestment.fund_slug` in `packages/shared/src/types.ts` is manager-level only.
- **Fund vehicle per asset**: record which fund of a manager holds each asset (for example, Carlyle fund X).
  Assets in weak funds can be sold on opportunistic terms. Add a vehicle field to `CompanyInvestment`.
- **Full shareholder structure per company**: the company page lists only PE/VC investors. Add the other holders.
- **Company-level deal history**: all deals of one company (add-ons, disposals), not only fund entries and exits.
- **Richer portfolio company data**: some funds publish a page per company, for example
  https://www.21invest.com/en/forno-d-asolo/. The 21 Invest extractor already parses these pages
  (`extract_company_detail`). Find the other funds with such pages and extract the same fields, so users can compare companies.
- **Careers pages**: monitor careers pages for more funds. The `job_posting` signal type already exists in `differ.py`.

## Public-registry sources
Add these as signal sources. Check the terms of use and cost of each one before you integrate it.
- AGCM (Italian competition authority) merger filings: open data https://dati.agcm.it/dataset/operazioni-di-concentrazione-2020-2024,
  weekly bulletin https://www.agcm.it/pubblicazioni/bollettino-settimanale/, Atom feed https://www.agcm.it/rss/atom-feed.
- EU merger cases: https://ec.europa.eu/competition/mergers/cases/about_this_site.html,
  legacy index https://ec.europa.eu/competition/mergers/cases_old/index.html,
  API list https://data.europa.eu/en/which-apis-are-available-and-where-can-i-find-information-about-them.
- Registro Imprese filings (paid API): https://accessoallebanchedati.registroimprese.it/abdo/api,
  company monitoring https://www.registroimprese.it/monitoraggi-d-impresa.
- CONSOB disclosures: https://www.consob.it/web/area-pubblica/download-quotate,
  major holdings https://www.consob.it/web/area-pubblica/partecipazioni-rilevanti.
- For PDF-heavy sources (these and PEM), evaluate Google's open-source LangExtract library for source-grounded extraction.

## Watch
- `enrich_portfolio` and `enrich_portfolio_final` can hit the pipeline step timeout. If a backlog builds up,
  increase the step timeout for these two steps in `apps/worker/fundradar_worker/pipeline.py`.
- Market-commentary articles that also name a transaction can pass the `_matches_exit` guard in `apps/worker/scripts/signal_corrections.py`.
  Check the filter audit output for this pattern.
