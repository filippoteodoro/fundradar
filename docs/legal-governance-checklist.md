# Legal Governance Checklist

Use this checklist for monthly/quarterly legal-compliance maintenance.

## Monthly

- Verify legal page links and routing still work (`terms`, `privacy`, `cookies`, `disclaimer`, `legal notice`).
- Confirm cookie consent banner behavior (accept/reject/reset) on desktop and mobile.
- Confirm tracking remains consent-gated.
- Review digest suppression list updates (`data/digest_unsubscribed_emails.json`).
- Review DSAR tracker status (`data/compliance/dsar_requests.csv`).

## Quarterly

- Review processor register (`data/compliance/processor_register.json`).
- Validate DPA/transfer references for active processors.
- Re-check retention statements vs real operational behavior.
- Run incident-response tabletop using `docs/compliance-incident-response.md`.
- Check legal contact channels (email/PEC/contact form) are operational.

## On Change Events

Trigger immediate legal review when:
- Adding a new third-party processor/tool
- Changing subscription billing or cancellation flow
- Enabling new tracking technologies
- Expanding data categories collected
- Launching new user-facing features processing personal data

## Release Gate for Privacy-Impacting Changes

Before shipping:
1. Processor register updated.
2. Legal pages updated if user-visible impact exists.
3. Legal bundle version bumped when policy substance changes.
4. Acceptance evidence still captured for subscription flow.
