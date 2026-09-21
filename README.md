# Fundradar

Free, public directory of PE/VC funds active in Italy, with source-cited signals, portfolio tracking, and deal history.

**Live**: [fundradar.vercel.app](https://fundradar.vercel.app)

## Status

Fundradar is a finished side project, released as free open source under the MIT License. It has no active maintainer.
The site has no accounts and no payments. Fork it, reuse it, or send a pull request.
The data in `data/` is a snapshot. It goes stale unless someone runs the pipeline again.

## What is in the repo

- **Web app** (`apps/web`): a statically generated Next.js site that reads committed JSON.
- **Worker** (`apps/worker`): a Python pipeline. It scrapes fund websites and news feeds, then filters, classifies, translates and enriches signals.
- **Data** (`data/`): the fund directory (`db.json`) and the pipeline output (`data/derived/`).

## Data sources and disclaimer

The data comes from public sources: fund websites, news RSS feeds, the AIFI member directory, PEM deal reports, and public LinkedIn pages.
Every signal links to its source. The data is provided as is, with no guarantee of accuracy or completeness.
The MIT License covers the code. Third-party content keeps the rights of its owners.

## API keys (pipeline only)

The web app needs no keys. The worker pipeline reads keys from `apps/worker/.env` (see `apps/worker/.env.example`):

| Key | Used for |
|-----|----------|
| `GEMINI_API_KEY` | Signal enrichment and fund audits |
| `DEEPL_API_KEY` or `AZURE_TRANSLATOR_KEY` | Italian-to-English translation |
| `OPENAI_API_KEY` | Optional signal classification |
| `APIFY_API_TOKEN` | Optional LinkedIn scraping |

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

The pipeline runs a preflight before any step. It stops on low free disk space and on missing or corrupt output files, before any API spend.

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
│   ├── pem/           # PEM source PDFs (gitignored, not in the repo)
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
| `pnpm worker:ingest` | Process PEM PDFs (needs local PDFs in `data/pem/`) |
| `pnpm worker:aifi` | Scrape AIFI member data |
| `pnpm worker:geocode` | Geocode fund addresses |
| `pnpm audit:quality` | Run fund data quality audit |

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

- The site is read-only: it serves the committed JSON in `data/` and writes nothing at runtime.
- The site runs without environment variables. The contact form needs `NEXT_PUBLIC_RECAPTCHA_SITE_KEY`, `RECAPTCHA_SECRET_KEY`, `RESEND_API_KEY`, and `CONTACT_EMAIL`.

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

- `AGENTS.md` — project-wide architecture and rules
- `apps/web/CLAUDE.md` — web app specifics (caching, data loading)
- `apps/worker/CLAUDE.md` — worker specifics (extraction, pipeline)
- `docs/data-flow.md` — data pipeline and source hierarchy
- `docs/runbook.md` — operations and troubleshooting
- `docs/tracking.md` — consent-gated analytics setup

## Contributing

Pull requests are welcome. Run `pnpm typecheck`, `pnpm test` and the worker tests (`cd apps/worker && pytest`) before you open one.
Read `AGENTS.md` first. It holds the data rules, for example that only PE, VC and growth-equity funds belong in `db.json`.
