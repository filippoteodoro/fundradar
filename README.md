# Fundradar

Free, public directory of PE/VC funds active in Italy with source-cited signals, portfolio tracking, and deal history.

**Live**: [fundradar.vercel.app](https://fundradar.vercel.app)

All data is freely accessible — no account required. Subscribe to receive weekly email digests of new signals.

## Quick Start

```bash
# Install dependencies
pnpm install

# Run web app (http://localhost:3000)
pnpm dev

# Run full pipeline (fetch + filter + enrich)
pnpm pipeline
```

Root-level worker commands such as `pnpm pipeline`, `pnpm worker:monitor`, and `pnpm pipeline:signals` activate `apps/worker/.venv` internally. Manual `source apps/worker/.venv/bin/activate` is optional.

The pipeline now runs a preflight before any step executes. It blocks on critically low free disk space and on missing canonical outputs when iCloud placeholders/conflict copies are present, so dangerous local-state issues fail before API spend.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web | Next.js 14 (App Router), TypeScript, React 18, Recharts |
| Data | File-based JSON (no database) |
| Worker | Python 3.10+, Playwright, BeautifulSoup |
| Types | `@fundradar/shared` (TypeScript) |
| Monorepo | pnpm workspaces |
| Hosting | Vercel (auto-deploys from `main`) |

## Project Structure

```
fundradar/
├── apps/
│   ├── web/           # Next.js frontend (deployed to Vercel)
│   └── worker/        # Python scraping worker (runs locally)
├── packages/
│   └── shared/        # Shared TypeScript types
├── scripts/           # TS seed/utility scripts
├── data/
│   ├── db.json        # Fund directory (source of truth)
│   ├── compliance/    # DSAR/incident/processor compliance trackers
│   ├── pem/           # PEM PDF source files
│   ├── derived/       # Worker output (JSON consumed by web)
│   └── AIFI/          # AIFI scraped data
├── docs/              # Documentation
└── archive/           # Historical audits, branding, sprint plans, and deprecated material
```

## Commands

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start web dev server |
| `pnpm build` | Build for production |
| `pnpm typecheck` | Type-check TypeScript |
| `pnpm test` | Run tests |
| `pnpm pipeline` | Full pipeline: monitor → filter → enrich |
| `pnpm pipeline --force-extract` | Re-extract all (after updating extractors) |
| `pnpm pipeline:signals` | Filter + enrich only |
| `pnpm worker:monitor` | Fetch websites and extract data |
| `pnpm worker:ingest` | Process PEM PDFs |
| `pnpm worker:aifi` | Scrape AIFI member data |
| `pnpm worker:geocode` | Geocode fund addresses |
| `pnpm audit:quality` | Run fund data quality audit |
| `pnpm digest:build` | Build weekly digest outputs |
| `pnpm digest:suppress` | Manage digest-only unsubscribe/suppression list |

## Deployment

The site auto-deploys to Vercel on push to `main`.

- **Repo**: [github.com/filippoteodoro/fundradar](https://github.com/filippoteodoro/fundradar)
- **Vercel Root Directory**: `apps/web`
- **Build**: `cd ../.. && pnpm -F @fundradar/shared build && pnpm -F web build`
- **Install**: `cd ../.. && pnpm install`

All fund pages are statically generated at build time via `generateStaticParams()`. Data refreshes on each deploy.

### Deployment workflow

1. Run `pnpm pipeline` locally to update data
2. Commit updated data files in `data/derived/`
3. Push to `main` — Vercel auto-deploys

### Vercel environment

- Filesystem writes (auth, watchlists) are disabled via `IS_READONLY` guard
- Auth API routes return 503
- Login/signup/watchlists redirect to `/subscribe`
- No environment variables required for basic deployment (Stripe keys only needed for payments)

## Setup

### Prerequisites
- Node.js 20+
- pnpm 8+
- Python 3.10+

### Python Worker
```bash
cd apps/worker
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

## Key Documentation

- `CLAUDE.md` — project-wide architecture and rules
- `apps/web/CLAUDE.md` — web app specifics (caching, data loading)
- `apps/worker/CLAUDE.md` — worker specifics (extraction, pipeline)
- `docs/data-flow.md` — data pipeline and source hierarchy
- `docs/runbook.md` — operations and troubleshooting
- `docs/compliance-dsar-runbook.md` — GDPR request handling workflow
- `docs/compliance-incident-response.md` — privacy/security incident workflow
- `docs/compliance-processor-register.md` — processor register governance
