# Sprint 1 Plan — Data Model + PEM Seed

## Goal
Parse PEM PDFs to extract real deals and fund managers, then display them in the web UI.

## Tasks

### T1.1 Create DB schema (skipped for v1)
- Using JSON file-based storage for now
- Supabase integration deferred to Sprint 2

### T1.2 Build PEM parser (deterministic)
- [x] Added pdfplumber dependency
- [x] Implemented `extract_deals_from_pdf()` in `apps/worker/fundradar_worker/ingest_pem.py`
- [x] Extracts: target_company, lead_investor, co_investors, amount, stake, stage, region, sector
- [x] Unit tests for parsing functions (slugify, parse_amount, parse_stake, parse_co_investors)
- **Output**: `data/derived/pem_deals.json` (879 deals), `data/derived/pem_investors.json` (385 investors)

### T1.3 Seed script to upsert fund_managers and deals
- [x] Updated `scripts/seed.ts` to load parsed PEM data
- [x] Creates Fund entries from unique investors
- [x] Creates Deal entries with source provenance
- [x] Generates sample Signal entries from deals
- **Output**: `data/db.json` with 385 funds, 879 deals, 50 signals

### T1.4 Web: display funds table from DB (server-side pagination)
- [x] Created `apps/web/src/lib/data.ts` for data loading
- [x] Updated homepage to load real funds (server component)
- [x] Added `FundsTable` client component with search and pagination
- [x] Updated fund detail page to show associated deals
- **Verify**: Search by name works (e.g., "Progressio" finds result)

## Acceptance Criteria
- [x] `pnpm worker:ingest` produces `pem_deals.json` with 879 parsed deals
- [x] Python tests pass: `cd apps/worker && pytest -v` (18 tests)
- [x] `pnpm seed` creates db.json with 385 funds from PEM
- [x] `pnpm build` succeeds (typecheck passes)
- [x] `pnpm test` all tests pass (5 tests)
- [x] `pnpm lint` passes

## Files Modified
| File | Change |
|------|--------|
| `packages/shared/src/types.ts` | Added Deal type |
| `apps/worker/pyproject.toml` | Added pdfplumber dependency |
| `apps/worker/fundradar_worker/ingest_pem.py` | PDF table extraction |
| `apps/worker/tests/test_ingest_pem.py` | Added parser tests |
| `scripts/seed.ts` | Load parsed PEM data |
| `apps/web/src/lib/data.ts` | New data loader utility |
| `apps/web/src/app/page.tsx` | Server component, loads real data |
| `apps/web/src/app/components/FundsTable.tsx` | Client search/pagination |
| `apps/web/src/app/funds/[slug]/page.tsx` | Show deals for fund |
| `package.json` | Fixed build script order |
