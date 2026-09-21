# Fundradar Web

Next.js 14 App Router application for the Fundradar directory.

## Tech Stack
- Next.js 14 (App Router)
- TypeScript, React 18
- Recharts (charts)
- Inline styles (no CSS framework)
- File-based JSON data (no database)

## Project Structure

```
src/
├── app/                 # App Router pages
│   ├── funds/          # Fund detail pages
│   ├── signals/        # Signals feed
│   ├── map/            # Fund map view
│   ├── about/
│   └── components/     # Page-specific components
├── components/         # Shared components (charts, tables, shared filters)
└── lib/                # Data loading and utilities
    ├── data.ts         # ALL data loading (central data layer)
    ├── fundFilters.ts  # Shared fund table/map filters (HQ country derivation + catalogs)
    ├── fundRangeFilters.ts # Shared range stops + AUM formatting for filter sliders
    └── signals_unified.ts  # Signal aggregation for /signals page
```

## Commands

```bash
pnpm dev       # Development server at localhost:3000
pnpm build     # Production build
pnpm test      # Run tests (vitest)
pnpm lint      # Lint code
pnpm typecheck # Type-check
```

## Data Loading

All data comes from JSON files in `data/` and `data/derived/`. See `src/lib/data.ts` for all loaders.

**Important**: Data is cached in-memory with no TTL. After any worker run, restart `pnpm dev` to see updated data.

## See Also

- [`CLAUDE.md`](./CLAUDE.md) in this directory for detailed web architecture notes
- Root [`AGENTS.md`](../../AGENTS.md) for project-wide rules
