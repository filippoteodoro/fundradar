# NEXT_SESSION

Goal: Fundradar is public at github.com/filippoteodoro/fundradar. The site is free, with no payments and no accounts (commit e8dc761).
History is rewritten (dead Gemini key redacted, noreply authors). The repo was deleted and recreated on 2026-09-21 to drop the old PR refs.
Pre-rewrite backup: `~/Code/Archive/fundradar-pre-rewrite-2026-09-21.bundle` (not on GitHub). Backlog: `to_do.md`.

## Domain `fundradar.co` (expires 2027-02-24, auto-renew OFF)
- The site no longer depends on it: canonical URL is `fundradar.vercel.app`, no contact form, no email sender.
- Until expiry, `fundradar.co` 308-redirects to `fundradar.vercel.app` (Vercel project domain setting). Nothing to do at expiry.

## Operator action
- Vercel: reconnect the Git link (fundradar → Settings → Git) to the recreated repo, or pushes do not deploy.
- Revoke the old `CLAUDE_CODE_OAUTH_TOKEN` (it was an Actions secret on the deleted repo; no workflow uses it).
