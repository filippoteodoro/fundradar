# Sprint 3 Plan — Snapshots + Change Detection

## Goal
Build the signals detection engine that monitors fund websites for changes.

## Tasks

### T3.1 Worker: URL fetcher + snapshot storage
- [x] Created `apps/worker/fundradar_worker/fetcher.py`:
  - `fetch_url()` - fetches pages with proper headers
  - `extract_text_from_html()` - extracts clean text, removes boilerplate
  - `compute_content_hash()` - generates hash for change detection
  - `SnapshotStore` - file-based storage for snapshots
- [x] Added dependencies: requests, beautifulsoup4
- [x] Tests in `tests/test_fetcher.py` (10 tests)

### T3.2 Diff engine for "meaningful changes"
- [x] Created `apps/worker/fundradar_worker/differ.py`:
  - `compute_diff()` - compares text content, returns DiffResult
  - `is_noise_line()` - filters dates, counters, boilerplate
  - `generate_what_changed()` - creates human-readable summaries
  - Detects: hiring, investments, team changes, fundraising, exits
- [x] Configurable thresholds (MIN_CHANGE_RATIO, MIN_ADDED_CHARS)
- [x] Tests in `tests/test_differ.py` (12 tests)

### T3.3 Create signal_event from diff
- [x] Created `apps/worker/fundradar_worker/monitor.py`:
  - `WebsiteMonitor` - orchestrates fetching, diffing, signal generation
  - `SignalStore` - persists detected signals
  - `run_monitor()` - entry point for monitoring
  - Auto-detects signal type based on content keywords
- [x] Added `pnpm worker:monitor` command

## Architecture

```
URL Fetch → Extract Text → Compare with Previous → Detect Changes → Generate Signal
    ↓              ↓                 ↓                    ↓              ↓
  HTTP         BeautifulSoup   SequenceMatcher      DiffResult     SignalRecord
    ↓              ↓                 ↓                    ↓              ↓
  Store       snapshots.json    content_hash      is_meaningful   detected_signals.json
```

## Files Created
| File | Purpose |
|------|---------|
| `apps/worker/fundradar_worker/fetcher.py` | URL fetching, text extraction, snapshot storage |
| `apps/worker/fundradar_worker/differ.py` | Diff computation, noise filtering |
| `apps/worker/fundradar_worker/monitor.py` | Monitoring orchestration, signal generation |
| `apps/worker/tests/test_fetcher.py` | Fetcher tests |
| `apps/worker/tests/test_differ.py` | Differ tests |

## Acceptance Criteria
- [x] `pnpm worker:monitor` runs without errors
- [x] Python lint passes: `ruff check .`
- [x] All 38 Python tests pass
- [x] `pnpm build` succeeds

## Usage

```bash
# Run the website monitor (checks sample URLs)
pnpm worker:monitor

# Files created:
# - data/derived/snapshots.json (snapshot index)
# - data/derived/snapshots_html/*.html (raw HTML)
# - data/derived/detected_signals.json (generated signals)
```

## Next Steps (Sprint 4)
- Create a `monitored_urls.json` config file with real fund URLs
- Schedule periodic monitoring (cron job or worker queue)
- Integrate detected signals with the web UI
- Add user watchlists and email digests
