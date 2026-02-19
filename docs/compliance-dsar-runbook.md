# DSAR Runbook (GDPR)

Use this runbook to handle privacy-rights requests under GDPR Articles 12-23.

## Scope

Request types covered:
- Access
- Rectification
- Erasure
- Restriction
- Portability
- Objection
- Consent withdrawal (where consent is legal basis)

## Systems and Data Sources

Primary sources in this repo:
- `data/auth.json`
- `data/subscribers.json`
- `data/watchlists.json`
- `data/digest_unsubscribed_emails.json`
- `data/derived/digest/sent_log.json` (operational metadata only)

Third-party sources to check where needed:
- Stripe (billing/subscription records)
- Vercel (hosting logs if relevant and legally required)
- Resend (contact-email processing events, where applicable)

## Intake

Accepted channels:
- Legal/privacy email address
- Contact form

Minimum intake fields:
- Requester email
- Request type
- Description of request scope
- Date/time received

Log every request in:
- `data/compliance/dsar_requests.csv`

## Identity Verification

Before disclosing or deleting data:
1. Verify control of the email tied to the account/subscription.
2. If risk is high, request additional proof (last billing date, masked transaction ref, etc.).
3. Record verification timestamp in tracker.

Do not process high-impact requests without verification.

## Deadlines

- Standard response deadline: 30 calendar days from receipt.
- Extension: up to 60 additional days for complex requests.
- If extended, notify requester within initial 30 days with reason and expected date.

## Handling Steps

1. Create request ID: `DSAR-YYYYMMDD-XXX`.
2. Register request in `data/compliance/dsar_requests.csv`.
3. Verify identity.
4. Collect relevant records from internal files and third-party processors.
5. Apply request action:
   - Access: provide exported data snapshot and categories/purposes.
   - Rectification: correct inaccurate records and confirm update.
   - Erasure: delete where legally permissible; retain only required legal/accounting records.
   - Objection/restriction: stop non-essential processing where applicable.
   - Portability: provide structured export for data provided by user.
6. Send response, including:
   - What was done
   - What cannot be done and why (if any)
   - Complaint right with Garante
7. Mark request closed in tracker with response timestamp.

## Response Content Checklist

- Request ID
- Date received and date answered
- Identity verification method
- Data sources checked
- Actions completed
- Remaining retained data and legal reason
- Garante complaint link: `https://www.garanteprivacy.it/`

## Retention of DSAR Records

Keep DSAR handling logs for compliance evidence (recommended: 24 months minimum, or longer if legal risk requires).

## Escalation

Escalate immediately if:
- Identity cannot be verified but request is high-impact.
- Request concerns potential data breach.
- Request scope includes legal/financial records with retention obligations.
