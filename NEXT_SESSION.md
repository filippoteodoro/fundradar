# NEXT_SESSION

Goal: Fundradar is public at github.com/filippoteodoro/fundradar. Only the domain step remains. The site is free, with no payments and no accounts (commit e8dc761).
History is rewritten: the dead Gemini key is redacted and the author emails are noreply.
Closed bot PRs #1/#2 keep the dead Gemini key in read-only `refs/pull/*`; harmless.
Pre-rewrite backup: `~/Code/Archive/fundradar-pre-rewrite-2026-09-21.bundle` (not on GitHub). Backlog: `to_do.md`.

## Before the domain expires (February 2027)
- Point `fundradar.co` to `fundradar.vercel.app` or to the GitHub repo. After expiry, anyone can buy the domain.
- Update `NEXT_PUBLIC_BASE_URL` and the `fundradar.co` links in `apps/web/src/app/llms*.txt` to the surviving URL.
