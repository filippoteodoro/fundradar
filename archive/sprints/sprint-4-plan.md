# Sprint 4 Plan — Website Monitoring (Top 100)

## Goal
Establish baseline monitoring for the top 100 priority funds following the websites-scraping.md spec.

## Completed Tasks

### T4.0 Feedback: Fix PEM source links
- [x] Updated seed.ts to use correct PEM URL: `https://www.liucbs.it/osservatori/private-equity-monitor-pem/`
- [x] Changed source_name to "PEM (Private Equity Monitor)"
- [x] Set source_url_status to "available"
- [x] Regenerated db.json

### T4.1 Phase 1: Storage Efficiency Improvements
- [x] Added conditional request support (ETag/Last-Modified)
- [x] Implemented check records for 304/unchanged responses
- [x] Added content-addressed blob storage for deduplication
- [x] Content hash comparison to skip duplicate HTML storage
- [x] Storage stats reporting

### T4.2 Top 100 Configuration
- [x] Created `monitor_urls_top100.json` with 100 priority funds
- [x] 98/100 matched with existing PEM entities
- [x] Added `--config` CLI argument to monitor

## Completed

### T4.3 Baseline Capture for Top 100
- [x] Run full monitoring pass on all 100 entities
- [x] Generate status report: 82.4% success rate (84/102 URLs)
- [x] Identified failing entities (DNS, SSL, 403, timeout issues)

### T4.4 URL Discovery (Phase 2)
- [x] Implement sitemap discovery (`/sitemap.xml`, WordPress sitemaps)
- [x] Implement RSS feed discovery
- [x] Implement homepage nav/footer crawl (depth=1)
- [x] Classify discovered URLs by page type
- [x] Update monitor_urls_top100.json with validated_urls for 13 Italian funds

Discovery results for Italian funds:
- 26 team pages discovered
- 15 news pages discovered
- 14 portfolio pages discovered
- 3 careers pages discovered

## Completed (continued)

### T4.5 Domain Policy Registry
- [x] Create `domain_policies.json` for rate limits, headless requirements
- [x] Handle known anti-bot sites (Cloudflare, etc.)
- [x] Implement `DomainPolicyRegistry` class with policy lookups
- [x] Integrate with fetcher (SSL verify, timeout, retry settings)
- [x] Integrate with monitor (skip blocked domains automatically)

Policy categories:
- 4 blocked (Cloudflare/403): carlyle, aresmgmt, oakleycapital, algebris
- 4 SSL issues: infraviacapital, neubergerberman, nuocapital, tagescapital
- 3 slow (extended timeout): auctus, nuveen, pollenstreetcapital
- 1 DNS error: oxy-capital

### T4.6 Run Discovery on Remaining Entities
- [x] Run URL discovery on all 71 entities with slugs
- [x] Update 61 entities with validated_urls (213 total URLs)
- [x] Created `discovery_top100.json` with discovery results
- [x] Fixed Oxy Capital missing slug

## Files Modified

| File | Change |
|------|--------|
| `scripts/seed.ts` | Fixed PEM source URL, added category field |
| `apps/worker/fundradar_worker/fetcher.py` | Phase 1 storage + domain policy support (SSL, timeout, retry) |
| `apps/worker/fundradar_worker/monitor.py` | Conditional requests, check records, domain policies integration |
| `apps/worker/fundradar_worker/domain_policies.py` | **New**: Domain policy registry |
| `apps/worker/fundradar_worker/url_discovery.py` | URL discovery via sitemap/RSS/nav crawl |
| `data/derived/monitor_urls_top100.json` | Updated with validated_urls for 61 entities |
| `data/derived/discovery_top100.json` | Discovery results for 71 entities |
| `data/derived/domain_policies.json` | **New**: Domain-specific fetch policies |
| `data/derived/problematic_domains.json` | **New**: Catalogue of domains needing special handling |

## Acceptance Criteria

- [x] PEM signals show correct source URL (not "unavailable")
- [x] `pnpm build` succeeds
- [x] All Python tests pass (61 tests)
- [x] Monitor uses conditional requests (304 handling)
- [x] Top 100 baseline captured (71 entities discovered, 61 with validated URLs)
- [x] Status report identifies coverage gaps (30 problematic domains catalogued)
- [x] Domain policies skip blocked domains automatically
- [x] SSL, timeout, retry settings applied per-domain

## Usage

```bash
# Run monitor on top 100
pnpm worker:monitor --config=data/derived/monitor_urls_top100.json

# Run with limit for testing
pnpm worker:monitor --config=data/derived/monitor_urls_top100.json --limit=10

# Generate report only
pnpm worker:monitor --report-only
```
