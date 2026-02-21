# Weekly Digest Runbook

Run this when you want to send the plain-text Fundradar weekly digest to active subscribers.

## What This Produces

- `data/derived/digest/latest_digest.txt` — plain-text email body
- `data/derived/digest/latest_recipients.csv` — sendable recipients (active minus suppressed)
- `data/derived/digest/latest_digest_meta.json` — build metadata + counts
- `data/derived/digest/sent_log.json` — sent-history dedupe log (not updated in `--dry-run`)
- `data/digest_unsubscribed_emails.json` — digest-only suppression list (opt-out without billing cancel)

## Prerequisites

- Subscriber statuses are up to date in `data/subscribers.json`
- Digest suppression list is current in `data/digest_unsubscribed_emails.json`
- Signals pipeline has been run recently (recommended):
  - `pnpm pipeline`
  - or at least `pnpm pipeline:signals`

## Build Digest

Default weekly window (last 7 days):

```bash
pnpm digest:build
```

Preview only (does not mutate sent log):

```bash
pnpm digest:build -- --dry-run
```

Custom window and size:

```bash
pnpm digest:build -- --from 2026-02-01T00:00:00Z --to 2026-02-08T00:00:00Z --max-signals 40
```

Control per-fund density:

```bash
pnpm digest:build -- --max-signals 25 --max-per-fund 2
```

Manage digest suppressions (opt-out list):

```bash
pnpm digest:suppress list
pnpm digest:suppress add user@example.com
pnpm digest:suppress remove user@example.com
```

## Selection Rule (v1)

A signal is included only if its effective signal date is in the selected window:

- `published_at` when present
- otherwise `observed_at`

Then signals already present in `sent_log.json` are excluded.

## Ranking + Readability Rules

- Event-first ranking: signals are ranked by overall signal importance with Italy/relevance weighting.
- Multi-fund handling: each signal is shown once, with all related funds listed on the same item.
- Diversity cap: `--max-per-fund` still applies using each signal's primary fund.
- Date shown is a single best date:
  - `published_at` when available
  - otherwise `observed_at` with `(observed)` label

## Manual Send Steps

1. Open `data/derived/digest/latest_digest.txt` for send-ready email body.
2. Open `data/derived/digest/latest_recipients.csv` and import into your email tool.
3. Verify any new unsubscribe requests are reflected in `data/digest_unsubscribed_emails.json`.
4. Send.
5. Keep `latest_digest_meta.json` for audit/debug context.

## Troubleshooting

- `Included signals: 0`:
  - widen lookback (`--days 14`)
  - check if signals were already sent (sent log dedupe)
  - verify signal files exist under `data/derived/`
- `Active recipients: 0`:
  - verify `data/subscribers.json` contains entries with `status: "active"`
- `Suppressed recipients` unexpectedly high:
  - run `pnpm digest:suppress list`
  - remove accidental entries with `pnpm digest:suppress remove <email>`
- Wrong source file:
  - loader priority is enriched -> filtered -> raw signals
