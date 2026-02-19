# Processor and Transfer Register

This register tracks third-party services that process personal data for Fundradar and supports GDPR accountability duties.

## Authoritative File

Maintain structured register in:
- `data/compliance/processor_register.json`

## Review Cadence

- Review at least quarterly
- Review immediately after adding/removing any integration
- Record `last_reviewed_at` per processor entry

## Required Fields per Processor

- Processor name
- Service/function
- Role (processor / independent controller where applicable)
- Data categories
- Purpose
- Transfer regions
- Transfer mechanism (adequacy, SCC, etc.)
- DPA URL / contract reference
- Subprocessor URL
- Retention notes
- Internal owner
- Status (`active`, `planned`, `retired`)

## Current Expected Processors (from codebase)

- Stripe (subscriptions/billing events)
- Vercel (hosting/infrastructure)
- Google (Tag Manager, Analytics, reCAPTCHA)
- LinkedIn (Insight Tag measurement, consent-gated)
- Resend (contact form email relay)

## Operational Rules

1. Do not activate new processors in production before adding them to register.
2. Store DPA/contract evidence outside code repo if sensitive, but keep references in register.
3. If a processor is retired, keep historical entry and mark status `retired`.

## Change Control

When updating processor register:
1. Update `data/compliance/processor_register.json`.
2. If user-facing impact exists, update privacy/cookie/terms pages and bump legal bundle version.
3. Record review date.
