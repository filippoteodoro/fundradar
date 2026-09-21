# Fundradar

Free, public directory of PE/VC funds active in Italy, with source-cited signals, portfolio tracking, and deal history.

**Live**: [fundradar.vercel.app](https://fundradar.vercel.app)

## Status

Fundradar is a finished side project, released as free open source under the MIT License. It has no active maintainer.
The site has no accounts and no payments. Fork it, reuse it, or send a pull request.
The data in `data/` is a snapshot. It goes stale unless someone runs the pipeline again.

## What is in the repo

- **Web app** (`apps/web`): a read-only Next.js site that reads committed JSON. It needs a Node server runtime (Vercel or similar), not static hosting.
- **Worker** (`apps/worker`): a Python pipeline. It scrapes fund websites and news feeds, then filters, classifies, translates and enriches signals.
- **Data** (`data/`): the fund directory (`db.json`) and the pipeline output (`data/derived/`).

## Data sources and disclaimer

The data comes from public sources: fund websites, news RSS feeds, the AIFI member directory, PEM deal reports, and public LinkedIn pages.
Every signal links to its source. The data is provided as is, with no guarantee of accuracy or completeness.
The MIT License covers the code. Third-party content keeps the rights of its owners.

## API keys (pipeline only)

The web app needs no keys. Put the keys in `apps/worker/.env` (template: `apps/worker/.env.example`). Some steps also read a root `.env`, but only the worker file reaches every step:

| Key | Used for |
|-----|----------|
| `OPENAI_API_KEY` | Signal enrichment (pipeline step 8; the step fails without it) |
| `DEEPL_API_KEY`, `DEEPL_API_KEY_2` | Italian-to-English translation (primary) |
| `AZURE_TRANSLATOR_KEY`, `AZURE_TRANSLATOR_REGION` | Translation fallback |
| `GEMINI_API_KEY` | Optional portfolio enrichment and the fund audit scripts |
| `APIFY_API_TOKEN` | Optional LinkedIn scraping (see `docs/linkedin-scraping.md`) |
| `FUNDRADAR_TELEGRAM_BOT_TOKEN`, `FUNDRADAR_TELEGRAM_CHAT_ID` | Optional pipeline alerts to a Telegram chat |

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

The pipeline runs a preflight before any step. It stops on low free disk space, and on missing output files when file-sync conflict copies are present.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web | Next.js 14 (App Router), TypeScript, React 18, Recharts |
| Data | File-based JSON (no database) |
| Worker | Python 3.10+, Playwright, BeautifulSoup |
| Types | `@fundradar/shared` (TypeScript) |
| Monorepo | pnpm workspaces |
| Hosting | Vercel |

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

The live site runs on Vercel. To host a fork, import it into a Vercel project and set the Root Directory to `apps/web`. `apps/web/vercel.json` sets the install and build commands:

- **Build**: `cd ../.. && pnpm -F @fundradar/shared build && pnpm -F web build`
- **Install**: `cd ../.. && pnpm install --frozen-lockfile`

Fund pages are listed at build time with `generateStaticParams()`, but the root layout reads cookies, so pages render on the server. Data refreshes on each deploy.

### Data refresh workflow

1. Run `pnpm pipeline` locally to update data.
2. Commit the updated files in `data/derived/`.
3. Push. The connected Vercel project redeploys.

### Vercel environment

- The site is read-only: it serves the committed JSON in `data/` and writes nothing at runtime.
- The site needs no environment variables. Optional: `NEXT_PUBLIC_GTM_ID` (Google Tag Manager, loaded only after cookie consent; a fork must set its own, see `docs/tracking.md`), `NEXT_PUBLIC_BASE_URL` (canonical URL; default `https://fundradar.vercel.app`), and `NEXT_PUBLIC_LEGAL_CONTROLLER_NAME` / `_EMAIL` / `NEXT_PUBLIC_LEGAL_JURISDICTION` (legal pages).

## Setup

### Prerequisites
- Node.js 20+
- pnpm 9 (the version is pinned in `package.json` → `packageManager`)
- Python 3.10+

### Python Worker
```bash
cd apps/worker
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # add ",ml" for the optional signal classifier
playwright install chromium
```

## Key Documentation

- [`AGENTS.md`](AGENTS.md) — project-wide architecture and rules
- [`apps/web/CLAUDE.md`](apps/web/CLAUDE.md) — web app specifics (caching, data loading)
- [`apps/worker/CLAUDE.md`](apps/worker/CLAUDE.md) — worker specifics (extraction, pipeline)
- [`docs/README.md`](docs/README.md) — index of task guides
- [`docs/ADDING_A_FUND.md`](docs/ADDING_A_FUND.md) — add a fund, end to end
- [`docs/check_signals.md`](docs/check_signals.md) — diagnose and fix signal quality issues
- [`docs/data-flow.md`](docs/data-flow.md) — data pipeline and source hierarchy
- [`docs/runbook.md`](docs/runbook.md) — operations and troubleshooting
- [`docs/tracking.md`](docs/tracking.md) — consent-gated analytics setup

## Contributing

Pull requests are welcome. Run `pnpm typecheck`, `pnpm test` and the worker tests (`cd apps/worker && pytest`) before you open one.
Read `AGENTS.md` first. It holds the data rules, for example that only PE, VC and growth-equity funds belong in `db.json`.
