# Tracking Setup

## Overview

Tracking is consent-gated. `apps/web/src/components/ConsentManager.tsx` loads Google Tag Manager only after
the visitor clicks Accept in the cookie banner. It stores the choice in `fundradar_cookie_consent_v1`
(local storage, 6-month validity). Vercel Analytics and Speed Insights are cookieless and always load.

## IDs

| Service | ID | Where |
|---|---|---|
| GTM Container | `GTM-P6LBQD4B` | Google Tag Manager → Fundradar container (`NEXT_PUBLIC_GTM_ID` overrides) |
| GA4 Property | `G-ZK8Z0S6B49` | Google Analytics → Fundradar (fired by the GA4 tag inside GTM) |

## Tags in GTM

The GA4 tag (Initialization - All Pages) is the only tag the site needs. The site has no purchases and no ad
conversions. Remove any conversion or ad tag (GA4 purchase event, LinkedIn Insight Tag) from the container.
The CSP in `apps/web/next.config.js` allows only Google hosts, so other third-party tags cannot load.

## Changing the Domain

1. Vercel: point the domain to the deployment and set `NEXT_PUBLIC_BASE_URL` to the new domain.
2. GA4 → Admin → Data Streams → Fundradar: update the stream URL.
3. GTM → Admin → Fundradar container: update the container URL if prompted.
