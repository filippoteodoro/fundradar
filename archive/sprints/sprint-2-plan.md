# Sprint 2 Plan — Fund Page + Signals Timeline

## Goal
Create clickable fund pages with signals timeline and add Italy beta branding.

## Tasks

### T2.1 Create fund detail route `/funds/[slug]` and basic overview
- [x] Fund detail page already exists from Sprint 1
- [x] Shows fund name, location, strategy tags
- [x] Shows associated deals from PEM data

### T2.2 Add Signals timeline component with type filter
- [x] Created `/signals` page with global signals feed
- [x] Added `SignalsFeed` client component with type filter chips
- [x] Filter by: All, Deals, Fundraising, Fund Closes, Exits, People Moves, Website Changes, Other
- [x] Color-coded signal type badges

### T2.3 Add "Italy beta" banner and About/Attribution footer
- [x] "Italy Beta" badge in header (already existed)
- [x] Footer with PEM attribution
- [x] Created `/about` page with:
  - What is Fundradar
  - Reliability contract
  - Data sources
  - Italy Beta explanation
  - Contact info

### T2.4 Navigation
- [x] Added nav links: Funds, Signals, About

## Acceptance Criteria
- [x] `/about` page renders with reliability contract info
- [x] `/signals` page shows filterable signals feed
- [x] Navigation between pages works
- [x] `pnpm build` succeeds

## Files Modified
| File | Change |
|------|--------|
| `apps/web/src/app/about/page.tsx` | New About page |
| `apps/web/src/app/signals/page.tsx` | New Signals feed page |
| `apps/web/src/app/signals/SignalsFeed.tsx` | Client component with filters |
| `apps/web/src/app/layout.tsx` | Added navigation links |
