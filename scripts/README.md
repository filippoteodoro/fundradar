# Scripts

Utilities for data seeding, parsing, and audits.

## Files

| Script | Purpose |
|--------|---------|
| `seed.ts` | Seed database with initial fund data |
| `parse-aifi.ts` | Parse AIFI fund directory data |
| `build-weekly-digest.ts` | Build plain-text weekly digest + recipients CSV + sent-log dedupe |
| `audit-fund-pages.py` | Fund page credibility audit |
| `audit-pem-status.py` | PEM status verification queue |
| `aifi-refresh-queue.py` | AIFI missing-fields queue |
| `audit-asset-status.py` | Build asset status audit + verification queue |
| `collect-asset-evidence.py` | Collect evidence for asset status decisions |
| `apply-asset-status.py` | Apply high-confidence status updates |
| `audit-fund-assets-gemini.py` | Gemini 3 Flash audit of fund assets (AUM desc, wrong/missing/corrections) |
| `recover-gemini-fund-asset-audit-from-logs.py` | Rebuild canonical Gemini audit output from exported AI Studio JSONL logs |
| `generate-gemini-manual-fund-prompts.py` | Generate per-fund paste-ready manual Gemini prompts for uncovered/incomplete funds |
| `import-manual-gemini-fund-responses.py` | Import manual per-fund Gemini JSON replies into deduplicated JSONL |
| `triage-gemini-fund-asset-audit.py` | Confidence/override triage for Gemini missing-asset suggestions |
| `run-audit-fund-assets-gemini-parallel.py` | Parallel shard runner + merge for Gemini fund-asset audit |
| `apply-gemini-missing-assets.py` | Apply Gemini missing-asset suggestions into portfolio with curation lock |
| `validate-gemini-audit-state.py` | Validate canonical Gemini JSONL + derived audit/progress drift |
| `rebuild-gemini-audit-from-canonical.py` | Rebuild canonical audit/progress from canonical JSONL |
| `validate-slug-consistency.py` | Validate active artifacts against `data/db.json` slugs |
| `cleanup-derived-slug-artifacts.py` | Prune non-DB slugs from active derived artifacts and backfill missing portfolio keys |

## Usage

```bash
cd scripts
npx tsx seed.ts
npx tsx parse-aifi.ts
```

## Dependencies

These scripts use `@fundradar/shared` for type definitions.

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

Gemini anti-blocking defaults (aligned with pipeline best practices):
- Sequential fund processing, ordered by AUM descending.
- `3s` delay between calls (`--sleep-seconds`).
- Retry with exponential backoff + jitter (`--retries`, `--min-backoff-sec`, `--max-backoff-sec`).
- HTTP timeout + hard SIGALRM timeout (`--timeout-sec`, `--hard-timeout-sec`).
- Auto-split for failed chunk audits (`--chunk-split-sizes`, default `40,20,8,1`).
- Missing-assets prompt fallback with smaller existing-name caps (`--missing-name-caps`, default `500,300,150,60`).
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
- After any reset-based rerun, rebuild canonical outputs from canonical JSONL before apply.

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
- Funds with `italian_entries=0` and no suggested missing assets are NOT auto-completed anymore.
- To explicitly mark true no-Italy cases as complete, whitelist slugs in `data/derived/gemini_fund_asset_zero_italy_verified.json`:

```json
{
  "verified_slugs": ["example-fund-slug"]
}
```

## Recover From AI Studio JSONL Logs

If shard/master files are incomplete but you exported AI Studio logs, rebuild canonical state from logs:

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
