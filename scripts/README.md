# Scripts

Utilities for data seeding, parsing, and audits.

Keep this folder for active or reusable scripts. One-off completed audits, cleanup passes and historical migration scripts belong in `archive/scripts/`.

## Files

TypeScript scripts run through `pnpm` (see `scripts/package.json`). Python scripts run from the repo root with `python3 scripts/<name>.py`. Most Gemini scripts need `GEMINI_API_KEY` in the root `.env` or `apps/worker/.env`.

| Script | Purpose |
|--------|---------|
| `seed.ts` | Build `db.json` from parsed PEM data (`pnpm seed`; refuses to overwrite a curated `db.json` without `--force`) |
| `parse-aifi.ts` | Parse AIFI fund directory data |
| `merge-aifi-metrics.ts` | Merge AIFI data and geocoded coordinates into `db.json` (`pnpm merge-aifi`) |
| `audit-fund-quality.ts` | Fund data quality audit (`pnpm audit:quality`) |
| `audit-fund-assets-gemini.py` | Gemini audit of fund assets (wrong, missing and corrected entries) |
| `run-audit-fund-assets-gemini-parallel.py` | Parallel shard runner + merge for the Gemini fund-asset audit |
| `reconcile-gemini-fund-asset-audit.py` | Merge master + shard audit outputs after an interrupted parallel run |
| `recover-gemini-fund-asset-audit-from-logs.py` | Rebuild canonical Gemini audit output from exported AI Studio JSONL logs |
| `rebuild-gemini-audit-from-canonical.py` | Rebuild canonical audit/progress from canonical JSONL (`pnpm gemini:rebuild`) |
| `validate-gemini-audit-state.py` | Validate canonical Gemini JSONL + derived audit/progress drift (`pnpm gemini:validate`) |
| `gemini_audit_completion.py` | Shared completion rules for Gemini audit outputs (imported by other scripts) |
| `generate-gemini-manual-fund-prompts.py` | Generate per-fund paste-ready Gemini prompts for uncovered or incomplete funds |
| `import-manual-gemini-fund-responses.py` | Import manual per-fund Gemini JSON replies into deduplicated JSONL |
| `triage-gemini-fund-asset-audit.py` | Confidence/override triage for Gemini missing-asset suggestions |
| `apply-gemini-missing-assets.py` | Apply Gemini missing-asset suggestions to the portfolio with a curation lock (`pnpm gemini:apply`) |
| `enrich-fund-metadata-gemini.py` | Fill missing AUM and investment ranges in `db.json` |
| `generate-fund-descriptions-gemini.py` | Generate fund descriptions in `db.json` |
| `enrich-top-fund-portfolios-gemini.py` | Enrich portfolios of top-AUM funds whose websites block scraping |
| `verify-portfolio-gemini.py` | Verify Gemini-generated portfolio entries with Google Search grounding |
| `check-fund-hq-gemini.py` | Verify fund headquarters |
| `run_new_fund_quality_pipeline.py` | End-to-end quality workflow for new funds (`pnpm pipeline:new-fund-quality`) |
| `verify_new_fund_completion.py` | Hard-gate completeness check for new funds (`pnpm verify:new-fund-completion`) |
| `check_new_fund_gate.py` | Deterministic CI gate for new or changed funds (`pnpm verify:new-fund-gate`) |
| `backfill_top_aum_signals.py` | Add vetted historical signals for top-AUM funds (`pnpm signals:backfill-top-aum`) |
| `internal_quality_agent.py` | Rule-based QA over signals and portfolio data → `data/derived/internal_agent_audit.json` |
| `validate-slug-consistency.py` | Validate active artifacts against `data/db.json` slugs (`pnpm slug:validate`) |
| `cleanup-derived-slug-artifacts.py` | Prune non-DB slugs from derived artifacts and backfill missing portfolio keys |
| `audit-short-summaries.py`, `audit-truncated-summaries.py` | Find suspicious `enriched_summary` values |
| `audit_italian_currency.py`, `audit_italian_currency_json.py` | Find Italian money expressions left in enriched summaries |
| `fix_lcatterton_names.py` | One-time fix of L Catterton portfolio names |

## Usage

```bash
pnpm seed                       # seed.ts
pnpm -F scripts parse-aifi      # parse-aifi.ts
pnpm merge-aifi                 # merge-aifi-metrics.ts
python3 scripts/validate-slug-consistency.py
```

The TypeScript scripts use `@fundradar/shared` for type definitions.

## AIFI Parser Exclusions

`parse-aifi.ts` enforces a non-fund exclusion list at parse time (without editing raw AIFI source files).
This includes known non-fund entities such as `finsea` / `gruppo finsea`.

## Slug Source Of Truth

Canonical slug registry is `data/db.json`.

Validate consistency:

```bash
python3 scripts/validate-slug-consistency.py
# or from repo root:
pnpm slug:validate
```

Cleanup active derived files to match DB slugs:

```bash
python3 scripts/cleanup-derived-slug-artifacts.py --apply
# or from repo root:
pnpm slug:cleanup:derived
```

What cleanup does:
- Prunes non-DB slugs from:
  - `data/derived/linkedin/fund_linkedin_urls.json`
  - `data/derived/linkedin/fund_linkedin_urls_prioritized.json`
  - `data/derived/gemini_fund_asset_logs/fund_checks_deduplicated.jsonl`
- Ensures all DB slugs exist in `data/derived/portfolio_items.json` -> `fund_portfolios` (empty lists allowed).

## Gemini Fund Asset Audit

All audit outputs, logs and the canonical JSONL below are gitignored, so a fresh clone has none of them. Only `data/derived/gemini_fund_asset_zero_italy_verified.json` is committed.

Run:

```bash
python3 scripts/audit-fund-assets-gemini.py --dry-run --limit-funds 15
python3 scripts/audit-fund-assets-gemini.py --limit-funds 25
python3 scripts/audit-fund-assets-gemini.py --slugs investindustrial,clessidra-sgr
python3 scripts/audit-fund-assets-gemini.py --slugs-file data/derived/my_slugs.txt
```

Outputs:
- `data/derived/gemini_fund_asset_audit.json`
- `data/derived/gemini_fund_asset_audit_progress.json`

Gemini anti-blocking defaults:
- Sequential fund processing, ordered by AUM descending.
- `3s` delay between calls (`--sleep-seconds`).
- Retry with exponential backoff + jitter (`--retries`, `--min-backoff-sec`, `--max-backoff-sec`).
- HTTP timeout + hard SIGALRM timeout (`--timeout-sec`, `--hard-timeout-sec`).
- Auto-split for failed chunk audits (`--chunk-split-sizes`, default `20,8,1`).
- Missing-assets prompt fallback with smaller existing-name caps (`--missing-name-caps`, default `60,20,1`).
- Native structured output mode (`responseMimeType=application/json` + `responseSchema`) for chunk and missing-assets calls.
- Automatic grounding fallback: if `google_search` is rejected, retries without grounding.

Parallel execution (resume-safe; no rerun of already completed funds by default):

```bash
python3 scripts/run-audit-fund-assets-gemini-parallel.py --workers 5
```

Default behavior:
- Pre-merges master + existing shard files before planning.
- Skips only strictly completed slugs (validated from output content, not just progress flags).
- Writes remaining queue to `data/derived/gemini_fund_asset_remaining_slugs.txt`.
- Runs worker scripts unbuffered (`-u`) for live logs.
- Does not reset shard files (safe resume after interruptions).

Force a full shard reset only when intentionally rerunning:

```bash
python3 scripts/run-audit-fund-assets-gemini-parallel.py --workers 5 --reset-shards
```

Warning:
- `--reset-shards` is destructive for shard progress/output files.
- The parallel runner merges shard outputs into the master audit file when it finishes. Use `reconcile-gemini-fund-asset-audit.py` if a run stops before the merge.

## Partial Refill Workflow (Safe, Non-Overwriting)

Use a separate output/progress pair when refilling only failed/partial slugs:

```bash
python3 -u scripts/audit-fund-assets-gemini.py \
  --slugs cvc-dif,triton,oakley-capital,perwyn,ring-capital,excellis-holding,private-equity-partners \
  --output-path data/derived/gemini_fund_asset_audit.partial_refill.json \
  --progress-path data/derived/gemini_fund_asset_audit_progress.partial_refill.json \
  --reset
```

If calls are unstable, run a focused second pass with no grounding and larger timeouts:

```bash
python3 -u scripts/audit-fund-assets-gemini.py \
  --slugs cvc-dif,oakley-capital,perwyn,ring-capital,excellis-holding,private-equity-partners \
  --output-path data/derived/gemini_fund_asset_audit.partial_refill_pass2.json \
  --progress-path data/derived/gemini_fund_asset_audit_progress.partial_refill_pass2.json \
  --no-grounding --timeout-sec 120 --hard-timeout-sec 150 --retries 3 --max-output-tokens 4096 --reset
```

Notes:
- This does not touch canonical files unless you explicitly set canonical `--output-path` / `--progress-path`.
- `--reset` is destructive for the selected output/progress target paths.
- Funds with `italian_entries=0` and no suggested missing assets are NOT auto-completed.
- To explicitly mark true no-Italy cases as complete, whitelist slugs in `data/derived/gemini_fund_asset_zero_italy_verified.json`:

```json
{
  "verified_slugs": ["example-fund-slug"]
}
```

## Recover From AI Studio JSONL Logs

Google AI Studio can export the logs of Gemini calls as JSONL. If shard/master files are incomplete and you have such exports, rebuild canonical state from them:

```bash
python3 -u scripts/recover-gemini-fund-asset-audit-from-logs.py \
  --input-jsonl "/path/to/export_batch_1.jsonl" \
  --input-jsonl "/path/to/export_batch_2.jsonl"
```

For full DB coverage (including funds currently without portfolio rows in DB):

```bash
python3 -u scripts/recover-gemini-fund-asset-audit-from-logs.py \
  --include-all-db-funds \
  --input-jsonl "/path/to/fund_checks_deduplicated.jsonl"
```

Outputs:
- Deduplicated merged logs: `data/derived/gemini_fund_asset_logs/fund_checks_deduplicated.jsonl`
- Recovered canonical audit: `data/derived/gemini_fund_asset_audit.json`
- Recovered canonical progress: `data/derived/gemini_fund_asset_audit_progress.json`
- Recovery report: `data/derived/gemini_fund_asset_audit_recovery_report.json`

Default behavior:
- Non-DB slugs are filtered out of recovered processing and deduplicated canonical JSONL.
- Use `--allow-non-db-slugs` only for historical/debug workflows.

## Canonical Contract

Canonical source of truth:
- `data/derived/gemini_fund_asset_logs/fund_checks_deduplicated.jsonl`

Derived/regenerated files:
- `data/derived/gemini_fund_asset_audit.json`
- `data/derived/gemini_fund_asset_audit_progress.json`
- `data/derived/gemini_fund_asset_audit_recovery_report.json`

Rules:
- Do not edit derived audit/progress files manually.
- Rebuild derived files from canonical JSONL after any reset/recovery work.
- API runs of `audit-fund-assets-gemini.py` write to the audit JSON directly and do NOT write to the canonical JSONL. A rebuild therefore deletes API run results. Rebuild only when the audit JSON is lost or corrupt (see pitfall 21 in the root `AGENTS.md`).

Validate canonical state:

```bash
python3 scripts/validate-gemini-audit-state.py
# or from repo root:
pnpm gemini:validate
```

Rebuild canonical derived files:

```bash
python3 scripts/rebuild-gemini-audit-from-canonical.py
# or from repo root:
pnpm gemini:rebuild
```

## Manual Gap Fill (Per-Fund Gemini Paste Flow)

1) Generate one prompt file per uncovered/incomplete fund:

```bash
python3 scripts/generate-gemini-manual-fund-prompts.py
```

2) Paste each file into Gemini and save JSON replies as:
- `data/derived/gemini_fund_asset_logs/manual_responses/<slug>.json`

3) Import manual replies into deduplicated JSONL:

```bash
python3 scripts/import-manual-gemini-fund-responses.py
```

Default behavior:
- Response file slug (`<slug>.json`) must exist in `data/db.json`.
- Use `--allow-non-db-slugs` only for temporary forensic imports.

4) Rebuild canonical output from updated deduplicated JSONL:

```bash
python3 scripts/rebuild-gemini-audit-from-canonical.py
```

## Gemini Triage (Ready vs OpenAI Check)

Run:

```bash
python3 scripts/triage-gemini-fund-asset-audit.py
```

Outputs:
- `data/derived/gemini_fund_asset_triage.json`

Default policy:
- `confidence=high` -> `ready_for_apply`
- `confidence=medium|low` -> `needs_openai_double_check`

Manual overrides:
- Optional file: `data/derived/gemini_fund_asset_manual_review.json`
- Per fund + asset you can force:
  - `ready_for_apply`
  - `needs_openai_double_check`
  - `rejected`

## Apply Gemini Missing Assets

Dry run (default):

```bash
python3 scripts/apply-gemini-missing-assets.py
# or from repo root:
pnpm gemini:apply:dry
```

Apply:

```bash
python3 scripts/apply-gemini-missing-assets.py --apply
# or from repo root:
pnpm gemini:apply
```

Notes:
- Default applies only `high` confidence suggestions.
- Non-Italy high-confidence suggestions are included by default.
- Use `--italy-only` to restrict by headquarters geography.
- Default guard requires canonical JSONL to exist and be non-empty:
  - `--canonical-jsonl-path ...`
  - `--require-canonical-jsonl/--no-require-canonical-jsonl`
- Apply mode creates backup before writing `portfolio_items.json`.
- Apply mode writes a timestamped report under `data/derived/gemini_apply_runs/`.
- Added entries are marked `curation_locked` so pipeline monitor/normalization steps do not overwrite them.
