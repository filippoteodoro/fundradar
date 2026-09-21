# Security

Report a vulnerability privately: go to the repo's **Security** tab and select **Report a vulnerability**.
Do not open a public issue for a vulnerability.

The site is read-only. It has no accounts, no payments and no API routes.
Never commit API keys. The worker reads them from `apps/worker/.env`, which is gitignored.
