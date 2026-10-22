# Data

All data files for Fundradar. This folder is gitignored except for schema/sample files.

## Structure

```
data/
├── db.json              # Main fund database (JSON format)
├── pem/                 # PEM PDF source files (DO NOT read directly)
├── derived/             # Processed/derived data from workers
│   ├── monitor_urls*.json    # URLs being monitored
│   ├── fund_profiles*.json   # Enriched fund profiles
│   └── signals*.json         # Extracted signals
└── AIFI/               # AIFI data organized by category
```

See [AIFI/README.md](AIFI/README.md) for the AIFI data and [monitor-urls.md](monitor-urls.md) for the base domain URLs of the monitored funds.

## Rules

1. **Never read PDFs directly** - Use `pnpm worker:ingest` to process them
2. **derived/ is the source of truth** - Workers write here, web app reads from here
3. **Don't commit large data files** - Only schema files and samples
4. **Backup before destructive operations** - Use `/backups/` folder
