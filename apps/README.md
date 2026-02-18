# Apps

This monorepo contains two applications:

## `/web/` - Next.js Frontend
The public-facing website built with Next.js App Router.
- See [web/README.md](./web/README.md) for setup and structure

## `/worker/` - Python Worker
Background processing for data ingestion, scraping, and monitoring.
- See [worker/README.md](./worker/README.md) for setup and modules

## Quick Start

```bash
# From project root
pnpm dev          # Start web app (localhost:3000)
pnpm worker:ingest   # Run PDF ingestion worker
```
