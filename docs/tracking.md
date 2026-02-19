# Tracking Setup

## Overview

All tracking runs through **Google Tag Manager (GTM)**. No tracking scripts are hardcoded except the GTM snippet itself.

## IDs & Accounts

| Service | ID | Account |
|---|---|---|
| GTM Container | `GTM-P6LBQD4B` | Google Tag Manager → Fundradar container |
| GA4 Property | `G-ZK8Z0S6B49` | Google Analytics → Fundradar |
| LinkedIn Partner | `60311` | LinkedIn Campaign Manager |

## What's Installed

### `apps/web/src/app/layout.tsx`
Single GTM snippet in `<head>` + noscript fallback in `<body>`. Replaces the old direct `gtag.js` GA4 script.

### Tags in GTM (`GTM-P6LBQD4B`)
| Tag | Type | Trigger |
|---|---|---|
| GA4 - Fundradar | Google Tag (`G-ZK8Z0S6B49`) | Initialization - All Pages |
| LinkedIn Insight Tag | LinkedIn Insight (`60311`) | All Pages |
| GA4 - Purchase Event | GA4 Event (`purchase`, ecommerce from dataLayer) | Custom Event: `purchase` |

### `apps/web/src/app/subscribe/success/PurchaseEvent.tsx`
Client component on the `/subscribe/success` page. Reads `session_id` from the Stripe redirect URL and pushes a `purchase` event to `window.dataLayer` with:
- `transaction_id`: Stripe `session_id` (prevents duplicate counting on page refresh)
- `value`: `9.00`
- `currency`: `EUR`
- `items`: `[{ item_name: 'Fundradar Weekly Signals', price: 9.00, quantity: 1 }]`

### LinkedIn Conversion
Configured in LinkedIn Campaign Manager as "Fundradar Subscribe":
- Method: Tag manager, page load
- URL rule: contains `/subscribe/success`
- Category: Purchase, Value: €9.00, Attribution: Last Touch

## When You Purchase a Custom Domain

Update these in order:

### 1. Vercel
Point the custom domain to the Vercel deployment. Update `NEXT_PUBLIC_BASE_URL` env var in Vercel dashboard to the new domain (e.g. `https://fundradar.com`). This fixes the Stripe `success_url` automatically (it reads from `NEXT_PUBLIC_BASE_URL`).

### 2. Google Analytics
GA4 → Admin → Data Streams → Fundradar → update the stream URL from `fundradar.vercel.app` to the new domain.

### 3. Google Tag Manager
GTM → Admin → Fundradar container → update the container URL if prompted. No tag changes needed — tags fire on all domains the GTM snippet is installed on.

### 4. LinkedIn Campaign Manager
- Insight Tag: verify it's detected on the new domain (Settings → Insight Tag)
- Conversion "Fundradar Subscribe": URL rule (`contains /subscribe/success`) stays valid — no change needed

### 5. Stripe
Stripe dashboard → update allowed redirect domains if restricted. The `success_url` is built dynamically from `NEXT_PUBLIC_BASE_URL` so no code change needed.

### 6. Facebook Pixel (when added)
Update the pixel's allowed domains in Facebook Events Manager.

## Adding New Pixels (Facebook, TikTok, etc.)

All new pixels go in GTM — no code changes needed:
1. GTM → Tags → New → select tag type
2. Set trigger to All Pages (base pixel) or Custom Event `purchase` (conversion)
3. Publish

For conversion events, the `purchase` dataLayer event already fires with full ecommerce data on `/subscribe/success`. New conversion tags just need to listen to the same `purchase` custom event trigger.
