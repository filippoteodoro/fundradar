# Documentation

Project-wide rules are in the root [`AGENTS.md`](../AGENTS.md). App details are in [`apps/web/CLAUDE.md`](../apps/web/CLAUDE.md) and [`apps/worker/CLAUDE.md`](../apps/worker/CLAUDE.md).

## Guides

| Document | Purpose |
|----------|---------|
| [`ADDING_A_FUND.md`](ADDING_A_FUND.md) | Add a fund end to end: research, `db.json` entry, extractor, pipeline, quality gates |
| [`check_signals.md`](check_signals.md) | Diagnose signal quality issues and find the function to fix |
| [`runbook.md`](runbook.md) | Run the worker, configure it, troubleshoot failures |
| [`linkedin-scraping.md`](linkedin-scraping.md) | LinkedIn people data: cadence, commands, raw-data protection |

## Reference

| Document | Purpose |
|----------|---------|
| [`data-flow.md`](data-flow.md) | Pipeline steps, source hierarchy, file → loader → page mapping |
| [`reliability-contract.md`](reliability-contract.md) | What the site guarantees about its data, and UI language rules |
| [`tracking.md`](tracking.md) | Consent-gated analytics (Google Tag Manager) |

## Archive

Historical audits, sprint plans and deprecated material are in [`archive/`](../archive/README.md). They do not describe the current code.
