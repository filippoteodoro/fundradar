# NEXT_SESSION

Goal: finish the Fundradar wrap-up. The site is free, with no payments and no accounts (commit e8dc761).
History is rewritten: the dead Gemini key is redacted and the author emails are noreply.
Closed bot PRs #1/#2 keep the dead Gemini key in read-only `refs/pull/*`; harmless.
Pre-rewrite backup: `~/Code/Archive/fundradar-pre-rewrite-2026-09-21.bundle` (not on GitHub). Backlog: `to_do.md`.

## Operator actions (the agent was blocked)
- **Stripe:** find the account that Fundradar used. Delete the webhook to `fundradar.co/api/stripe/webhook`.
  Archive the product and price. Cancel any subscriptions. Roll or delete the secret key.
- **GTM `GTM-P6LBQD4B`:** delete the "GA4 - Purchase Event" tag and the LinkedIn Insight Tag.

## Before the repo goes public (operator decision)
- Run `gitleaks git --log-opts=--all` again, then `gh repo edit filippoteodoro/fundradar --visibility public --accept-visibility-change-consequences`.

## Before the domain expires (February 2027)
- Point `fundradar.co` to `fundradar.vercel.app` or to the GitHub repo. After expiry, anyone can buy the domain.
- Update `NEXT_PUBLIC_BASE_URL` and the `fundradar.co` links in `apps/web/src/app/llms*.txt` to the surviving URL.
