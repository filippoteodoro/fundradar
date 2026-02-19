# Privacy/Security Incident Runbook

Use this runbook for incidents involving personal data confidentiality, integrity, or availability.

## Objective

- Contain fast
- Assess impact
- Meet GDPR notification duties
- Preserve evidence

## Incident Log

Track every incident in:
- `data/compliance/security_incidents.json`

## Severity Levels

- `low`: no confirmed personal-data exposure, contained quickly
- `medium`: limited exposure risk, likely contained
- `high`: confirmed or probable personal-data breach affecting users
- `critical`: large-scale or sensitive breach requiring urgent legal/regulatory handling

## Response Timeline

### T+0 to T+2h: Detect and Contain

1. Open incident ID: `INC-YYYYMMDD-XXX`.
2. Record first facts in incident log.
3. Contain:
   - Revoke exposed secrets/tokens
   - Disable affected integration/endpoint
   - Block malicious traffic patterns
4. Preserve evidence (logs, request IDs, system state snapshots).

### T+2h to T+24h: Assess

1. Identify data categories involved.
2. Estimate affected subjects and records.
3. Assess likelihood and severity of harm.
4. Decide whether GDPR Art. 33 notification threshold is met.

### T+24h to T+72h: Notify if Required

If personal-data breach is likely to risk rights/freedoms:
- Notify Garante without undue delay and, where feasible, within 72 hours.
- If delayed, document reasons in incident log.

If high risk to individuals:
- Prepare user communication under GDPR Art. 34.

### Post-Incident (within 7-14 days)

1. Root-cause analysis.
2. Corrective actions with owners and deadlines.
3. Policy/process updates.
4. Close incident only after verification of fixes.

## Garante Notification Minimum Fields

- Nature of breach
- Categories/approximate numbers of data subjects and records
- Likely consequences
- Measures taken or proposed
- Contact point for follow-up

## User Notification Minimum Fields (if required)

- What happened
- What data was involved
- What actions users should take
- What Fundradar already did
- Contact channel for support

## Decision Log Requirements

Document explicitly:
- Why notification was or was not made
- Who made the decision and when
- What evidence supported the decision

## Recovery Checklist

- Secrets rotated
- Access keys audited
- Affected systems patched
- Monitoring rules added
- Legal docs/registers updated where needed
