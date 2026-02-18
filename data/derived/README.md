# Derived Data Files

This directory contains all processed output from the worker module. These files are consumed by the web app and other tools.

## Files Used by Web App

| File | Used By | Description |
|------|---------|-------------|
| `portfolio_items.json` | `/funds/[slug]` page | Portfolio companies per fund |
| `fund_people_stats.json` | `/funds/[slug]` page | Team analytics (charts) |
| `pem_deals.json` | `/funds/[slug]` page | Deal activity from PEM reports |
| `detected_signals_filtered.json` | `/signals` page | Website change signals |

## Primary Data Files

| File | Purpose |
|------|---------|
| `aifi_members.json` | Raw AIFI member list |
| `aifi_members_enriched.json` | AIFI members with enriched data |
| `detected_signals.json` | Raw detected signals (before filtering) |
| `detected_signals_enriched.json` | Signals with AI enrichment |
| `detected_signals_filtered.json` | Final filtered signals for display |

## Monitor State Files

| File | Purpose |
|------|---------|
| `monitor_urls.json` | Parsed URLs from monitor-urls.md |
| `circuit_state.json` | Circuit breaker state per domain |
| `domain_policies.json` | Rate limits and rules per domain |
| `blocked_sites.json` | Sites blocked due to errors |
| `poison_urls.json` | URLs that consistently fail |

## Quality & Diagnostics

| File | Purpose |
|------|---------|
| `broken_urls_report.json` | URLs returning errors |
| `bulk_test_results.json` | Bulk extraction test results |
| `extraction_test_results.json` | Individual extraction tests |
| `easy100_quality_report.json` | Quality metrics for top 100 funds |
| `extraction_improvements.json` | Suggested extraction improvements |

## PEM Data (from PDF ingestion)

| File | Purpose |
|------|---------|
| `pem_deals.json` | Extracted deal information |
| `pem_investors.json` | Investor mentions (worker-only) |
| `pem_manifest.json` | Processing metadata |

## Discovery & Linking

| File | Purpose |
|------|---------|
| `entity_links.json` | Cross-reference entity IDs |
| `fund_aliases.json` | Fund name variations |
| `discovered_urls.json` | Newly discovered URLs |

## Subdirectories

### `/blobs/`
Raw HTML snapshots for diffing. One subdirectory per monitored URL.

### `/extracted/`
Structured data extracted from pages.

## File Freshness

Most files are updated by `pnpm worker:monitor`. Check modification dates to assess freshness.
Files older than 7 days may contain stale data.
