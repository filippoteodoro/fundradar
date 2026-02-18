# Sprint 0 Plan — Runnable Skeleton

## Goal
Produce a demoable v0 skeleton that compiles, has tests, and can be run with a single command.

## Tasks

### T0.1 Initialize monorepo structure
- pnpm workspace with apps/web, apps/worker, packages/shared
- TypeScript config extending shared base
- **Verify**: `pnpm install` succeeds

### T0.2 Create shared types (packages/shared)
- Fund, Vehicle, Signal TypeScript types
- Export from index.ts
- **Verify**: `pnpm -F @fundradar/shared build` succeeds

### T0.3 Setup apps/web (Next.js + Tailwind)
- Next.js 14 App Router with TypeScript
- Tailwind CSS for styling
- Homepage with search input + mock data table
- Fund detail page `/funds/[slug]`
- **Verify**: `pnpm -F web dev` shows homepage with table

### T0.4 Setup apps/worker (Python)
- Python project with pyproject.toml
- Minimal PEM parser placeholder (reads /data/pem, outputs JSON to /data/derived)
- **Verify**: `cd apps/worker && python -m fundradar_worker.ingest_pem` creates JSON

### T0.5 Create seed script
- TypeScript script in scripts/ that reads derived JSON
- Loads into mock DB (JSON file for now, with Supabase path documented)
- **Verify**: `pnpm seed` creates data/db.json

### T0.6 Setup CI (GitHub Actions)
- Lint (ESLint for TS, ruff for Python)
- Typecheck (tsc)
- Unit tests (vitest for TS, pytest for Python)
- **Verify**: `pnpm lint && pnpm typecheck && pnpm test` all pass

### T0.7 Single run command
- `pnpm dev` boots web
- `pnpm worker:ingest` runs Python parser
- Document in README
- **Verify**: README instructions work from fresh clone

## Acceptance Criteria
- [x] `pnpm install` succeeds
- [x] `pnpm dev` starts web server, homepage shows table with mock data
- [x] `pnpm -F web build` succeeds (typecheck passes)
- [x] `pnpm test` runs at least one test
- [x] `pnpm worker:ingest` produces JSON in /data/derived
- [x] GitHub Actions CI workflow file exists
