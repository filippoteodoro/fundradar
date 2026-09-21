# Tracking Setup

## Overview

Tracking is consent-gated. `apps/web/src/components/ConsentManager.tsx` loads Google Tag Manager only after
the visitor clicks Accept in the cookie banner. It stores the choice in `fundradar_cookie_consent_v1`
(local storage, 6-month validity). Vercel Analytics and Speed Insights are cookieless and always load.

## Container ID

`ConsentManager.tsx` reads `NEXT_PUBLIC_GTM_ID`. If the variable is not set, Google Tag Manager never loads.
To use analytics in a fork, set `NEXT_PUBLIC_GTM_ID` to your own container.

## Tags

A GA4 tag that fires on all pages is the only tag the site needs. The site has no purchases and no ad
conversions. The CSP in `apps/web/next.config.js` allows only Google Tag Manager and Google Analytics hosts,
so other third-party tags cannot load.

When you change what loads, keep `/cookie-policy` and `/privacy-policy` in sync.

## Changing the Domain

1. Point the domain to the Vercel deployment and set `NEXT_PUBLIC_BASE_URL` to the new domain.
2. In GA4 (Admin → Data Streams), update the stream URL.
3. In Google Tag Manager (Admin → container settings), update the container URL if prompted.
