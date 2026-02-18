# Fundradar

Italy-first PE/VC funds directory with source-cited signals.
Current curated scope: in-scope PE/VC/Growth funds in `data/db.json`.

## Quick Start

```bash
# Install dependencies
pnpm install

# Run web app (http://localhost:3000)
pnpm dev

# Run full pipeline (fetch + filter + enrich)
pnpm pipeline
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web | Next.js 14 (App Router), TypeScript, React 18, Recharts |
| Data | File-based JSON (no database) |
| Worker | Python 3.10+, Playwright, BeautifulSoup |
| Types | `@fundradar/shared` (TypeScript) |
| Monorepo | pnpm workspaces |

## Project Structure

```
fundradar/
├── apps/
│   ├── web/           # Next.js frontend
│   └── worker/        # Python scraping worker
├── packages/
│   └── shared/        # Shared TypeScript types
├── scripts/           # TS seed/utility scripts
├── data/
│   ├── pem/           # PEM PDF source files
│   ├── derived/       # Worker output (JSON consumed by web)
│   └── AIFI/          # AIFI scraped data
├── docs/              # Documentation
└── archive/           # Historical sprint plans
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
