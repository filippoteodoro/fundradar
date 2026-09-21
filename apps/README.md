# Apps

This monorepo contains two applications.

## `web/` — Next.js frontend
The public website, built with the Next.js App Router. See [web/README.md](./web/README.md).

## `worker/` — Python worker
Data ingestion, scraping, signal processing and enrichment. See [worker/README.md](./worker/README.md).

## Quick Start

```bash
# From the repo root
pnpm dev          # Start web app (localhost:3000)
pnpm pipeline     # Run the full worker pipeline
```
