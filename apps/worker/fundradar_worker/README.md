# Fundradar Worker Module

This is the core Python module for data collection, processing, and monitoring.

## Module Structure

### Core Orchestration
| File | Purpose |
|------|---------|
| `monitor.py` | Main orchestrator - coordinates fetching, diffing, and signal detection |
| `cli.py` | Command-line interface for all worker operations |
| `data_writer.py` | Writes processed data to JSON files in `/data/derived/` |

### Web Scraping & Fetching
| File | Purpose |
|------|---------|
| `fetcher.py` | HTTP fetching with caching and retry logic |
| `playwright_fetcher.py` | Browser-based fetching for JavaScript-heavy sites |
| `playwright_pool.py` | Browser instance pool management |
| `detail_page_fetcher.py` | Fetches detail pages (portfolio companies, team members) |

### Content Analysis
| File | Purpose |
|------|---------|
| `differ.py` | Detects changes between page snapshots |
| `enrichment.py` | AI-powered content enrichment (company info, signals) |
| `relevance.py` | Scores content relevance for filtering |
| `noise_filter.py` | Filters low-quality/noise signals |
| `portfolio_validation.py` | Validates and cleans portfolio entries before writing (shared patterns with web app) |

### Site-Specific Configuration
| File | Purpose |
|------|---------|
| `site_config_schema.py` | Type definitions for site extraction configs |
| `site_extractor.py` | Extracts structured data using site-specific rules |
| `domain_policies.py` | Per-domain rate limits and rules |

### External Data Sources
| File | Purpose |
|------|---------|
| `aifi_scraper.py` | Scrapes AIFI (Italian PE Association) member data |
| `ingest_pem.py` | Parses PEM (Private Equity Monitor) PDF reports |

### Utilities
| File | Purpose |
|------|---------|
| `normalizer.py` | Text normalization and cleaning |
| `url_utils.py` | URL parsing and manipulation |
| `url_generator.py` | Generates monitored URLs from extractor URLS declarations |
| `parse_monitor_urls.py` | Parses `data/monitor-urls.md` |
| `entity_resolver.py` | Matches entities across data sources |

### Reliability
| File | Purpose |
|------|---------|
| `circuit_breaker.py` | Prevents cascade failures on flaky sites |
| `rate_limiter.py` | Respects rate limits per domain |
| `baseline.py` | Manages baseline snapshots for diffing |
| `quality_monitor.py` | Tracks extraction quality metrics |
| `health_report.py` | Generates health/status reports |

## Subdirectories

### `strategies/`
Generic extraction strategies (`next_data`, `json_ld`, `html_cards`, `logo_grid`) and `strategies/extractors/`, which holds one fund-specific extractor per fund.

### `extractors/`
Page-type specific extractors (news, portfolio, team pages).

### `linkedin/`
LinkedIn scraping and profile analysis. See [`docs/linkedin-scraping.md`](../../../docs/linkedin-scraping.md).

## Common Commands

```bash
# Run the monitor
pnpm worker:monitor

# Ingest PEM PDFs
pnpm worker:ingest

# Run specific CLI commands
cd apps/worker
python -m fundradar_worker.cli --help
```

## Output Files

All output goes to `data/derived/`. See [`data/derived/README.md`](../../../data/derived/README.md) for file descriptions.
