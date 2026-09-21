# NEXT_SESSION

Goal: Fundradar is public at github.com/filippoteodoro/fundradar. The site is free, with no payments and no accounts (commit e8dc761).
History is rewritten: the dead Gemini key is redacted and the author emails are noreply.
Pre-rewrite backup: `~/Code/Archive/fundradar-pre-rewrite-2026-09-21.bundle` (not on GitHub). Backlog: `to_do.md`.

## Domain `fundradar.co` (expires 2027-02-24, auto-renew OFF)
- The site no longer depends on it: canonical URL is `fundradar.vercel.app`, no contact form, no email sender.
- Until expiry, `fundradar.co` 308-redirects to `fundradar.vercel.app` (Vercel project domain setting). Nothing to do at expiry.

## Open: pre-rewrite commits still reachable via closed PRs #1/#2
- `refs/pull/1/head` and `refs/pull/2/head` hold 197 pre-rewrite commits authored with the private Gmail, plus the dead Gemini key.
- Only GitHub Support can delete PR refs (docs: "Removing sensitive data from a repository"). The operator decides: make private, file a ticket, then make public again; or accept.
