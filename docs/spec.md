# Fundradar — Italy-first (Signals Engine)

> **Note**: This spec was written during initial planning. The actual implementation uses **file-based JSON** instead of a database — there is no Supabase, no SQL schema, no Tailwind CSS. Sprint task references to database migrations and Supabase setup were superseded by the file-based approach. See root `AGENTS.md` for the current tech stack. Fundradar is a free, open-source project with no accounts and no payments.

## 1) Summary
Fundradar is a table-first website for discovering PE/VC funds (Italy-first) and tracking **publicly observable signals** with strong provenance.
It is not an “enterprise database” replacement. It is a **source-cited signal engine**.

## 2) Target user (ICP for v1)
Primary user (pick ONE for v1, design UX for them):
- Boutique service providers (recruiters, advisors, lawyers, fund admins, BD vendors) who want “who’s active now” signals.

Secondary (free distribution, not main UX):
- Funds monitoring competitors (later)
- Candidates / founders (later)

## 3) Non-goals (explicit)
- No performance/quality scores based on IRR/TVPI unless sourced and safe.
- No “complete recruiting database”.
- No global coverage in v1.
- No attempt to out-complete PitchBook/Preqin/Dealroom.

## 4) Data philosophy (what “reliable” means here)
Reliable = “Every claim is clickable.”
For each signal:
- URL + date(s) + snapshot + extraction method
- clear “what changed” note
- ability to correct/merge entities

## 5) Core UX / Pages (keep it minimal)

### 5.1 Home `/`
Table-first layout:
- Top bar: logo + “Italy beta” banner (“Available in Italy only — expanding soon”)
- Global search input (single field)
- Optional filter chips (Strategy, HQ country, Sector, Activity score, Last signal date)
- Funds table (server-side pagination)
  Columns (v1):
  - Fund / Manager name
  - HQ (city, region)
  - Strategy tags (PE/VC/Growth/Infra/Other)
  - Sector tags (normalized)
  - Activity score (0–100)
  - Last signal (date + type)
  - Source count (how many sources tracked)

Click row → Fund detail page.

### 5.2 Fund page `/funds/[slug]`
Sections (no tabs unless needed):
1) Overview card:
   - Name, HQ, website
   - “Manager → Vehicles” structure (if known)
   - Strategy + sector focus (declared)
   - Footprint (Italy focus / EU / global – only if sourced)
   - “Sources tracked” list

2) Signals timeline:
   - chronological list with filters by type
   - each item: title, 1-line summary, date, source link, and “what changed” detail

3) Deals (if available from PEM or other sources):
   - minimal list (target + date + stage + investor role)

4) Corrections:
   - “Suggest correction” form

### 5.3 Signals feed `/signals`
Global feed of latest signals (Italy-only), filterable by type and sector.

### 5.4 About `/about`
- Be transparent about reliability contract and sources.
- Attribution for PEM dataset usage.

## 6) Feature set (MECE, v1)
A) Discovery
- Global search + filter chips

B) Profiles (safe fields only)
- Manager/SGR entity + Vehicles underneath (when known)
- Thesis/strategy as “declared” fields
- Team: link-only or sourced extraction with timestamps (do not claim completeness). Dummy analytics may be used for cost reasons, but must not be labeled as dummy in the UI.

C) Signals (the product)
Signal types (v1):
- Fundraise/close (announced)
- People moves (announced)
- Deals/exits (announced / PEM)
- Hiring/job postings (careers pages). Classified as `job_posting` when role/location is extractable.
  Support/admin/office roles and internships are excluded.
- Website changes (non-hiring) remain low-priority and should not be shown unless reclassified.

D) Trust (embedded everywhere)
- Source links + dates + snapshots
- Recency indicators
- Corrections workflow (light admin + user suggestions)
- AI is never disclosed in UI. AI is only used to accelerate data collection and source discovery; the UI should show sources, not “AI-generated” labels.
 - No “as of” labels in the UI; keep data updated instead.

## 7) Data model (high level)

### 7.1 Entities
- fund_manager (SGR / firm)
- vehicle (fund/vehicle) [optional v1]
- person (team members) [optional v1]
- deal (PEM + other sources)
- signal_event (core)
- source (site/news/linkedin/pem)
- snapshot (raw HTML/text/PDF extraction)

### 7.2 Key design decisions
- Keep both:
  - raw snapshots (immutable)
  - extracted normalized fields (mutable, versioned)
- Entity resolution is first-class:
  - store aliases for fund names
  - store confidence for automated matches

## 8) Ingestion pipeline (Italy-first)

### 8.1 Seed from PEM PDFs (authorized)
Input: /data/pem/Deals-PEM_2024.pdf and Rapporto-PEM_2024-1.pdf
Goal: create baseline entities:
- deals (targets, investors)
- fund_manager entries for investors
- provenance linking back to PEM

NOTE: Parsing must be deterministic and testable.
Keep a “fixtures” folder with a known extracted page text.

### 8.2 Sources to scrape (v1)
Priority order:
1) Fund websites (about / team / strategy / portfolio / careers / news)
2) Press releases & RSS feeds from selected Italian PE/VC news sites (only what’s publicly accessible)
3) LinkedIn (only if allowed; treat as enrichment; store links + minimal extracted fields + timestamps)

### 8.3 Scraping approach (do not overcomplicate)
- For each tracked URL:
  - fetch
  - store snapshot
  - extract text
  - diff against last snapshot
  - if meaningful change → create signal_event with “what changed” and link

Meaningful change heuristic (v1):
- ignore header/footer boilerplate
- detect changes in main content blocks
- threshold on token diff size

### 8.4 LLM enrichment (optional, budgeted)
Use LLM only for:
- normalizing sector tags from free text
- generating 1-line “what changed” summaries from diffs
- suggesting entity matches (with confidence)
Hard rule:
- Never let LLM invent facts; it can only rewrite/summarize extracted text.

## 9) Search strategy (keep costs low)
Phase 1 (v1):
- Postgres full-text search + trigram for fuzzy match
- Search fields: name, aliases, city/region, declared sectors, strategy tags, website domain

Phase 2 (later):
- Add vector search (pgvector) only if users complain the search is dumb.

## 10) Deployment & cost (MVP budget)
Suggested baseline:
- Vercel Pro for Next.js web: $20/month (plus usage). 
- Supabase Pro: from $25/month (includes $10 compute credits). 
- One small VPS (EU) for worker: start ~€4–€10/month (Hetzner class) or $4–$6/month (DigitalOcean class). 

Est. fixed cost for MVP: roughly $50–$80/month + domain + small LLM usage (optional).
(All prices should be re-checked before purchase.)

## 11) Sprints and atomic tickets
Rules:
- Every sprint ends with a demoable product.
- Every ticket is atomic and ends with tests or a deterministic verification checklist.

### Sprint 0 — Repo + Foundations (demo: app boots + CI green)
T0.1 Initialize monorepo structure (apps/web, apps/worker, packages/shared)
- DoD: `pnpm dev` boots web; `pytest` runs (even empty) in worker

T0.2 Next.js setup + Tailwind + basic layout shell
- DoD: Home page renders with placeholder table component

T0.3 Supabase project config + env handling + local types
- DoD: App can connect to Supabase; healthcheck route works

T0.4 CI pipeline (lint + typecheck + tests)
- DoD: GitHub Actions green on PR

### Sprint 1 — Data model + PEM seed (demo: funds + deals visible)
T1.1 Create DB schema migrations (fund_manager, deal, source, snapshot, signal_event)
- DoD: migrations apply cleanly; schema documented in docs/data-model.md

T1.2 Build PEM parser (deterministic)
- Input: Deals-PEM_2024.pdf
- Output: normalized deals + investor names
- DoD: unit test parses at least 1 known page fixture into expected fields

T1.3 Seed script to upsert fund_managers and deals
- DoD: running seed creates N fund managers and N deals in DB

T1.4 Web: display funds table from DB (server-side pagination)
- DoD: Home table shows real rows; search by name works (basic)

### Sprint 2 — Fund page + signals timeline skeleton (demo: clickable fund pages)
T2.1 Create fund detail route `/funds/[slug]` and basic overview
- DoD: clicking a row opens fund page with data from DB

T2.2 Add empty Signals timeline component
- DoD: timeline renders and supports type filter UI (even if empty)

T2.3 Add “Italy beta” banner and About/Attribution footer
- DoD: visible on all pages

### Sprint 3 — Snapshots + change detection (demo: first real signals)
T3.1 Worker: URL fetcher + snapshot storage (text + html)
- DoD: can fetch a single URL and store snapshot in DB

T3.2 Diff engine for “meaningful changes”
- DoD: deterministic diff output; tests with stored HTML fixtures

T3.3 Create signal_event from diff
- DoD: signal appears in `/signals` feed and on fund page timeline

### Phase 6 — Asset-Centric Features

**Implemented:**
- `/companies` — browse all PE/VC-backed companies with filters (sector, status, country, search)
- `/companies/[slug]` — company detail page showing all fund investors, deal history, and sources
- Cross-fund company deduplication via `normalizeCompanyName()` + `compactName()` matching
- Statically generated at build time (same pattern as fund pages)
- Italy filter defaults on (consistent with fund portfolio pages)

**Future roadmap (from PE professional feedback):**
- Multi-strategy breakdown: show which fund vehicle/strategy made each investment
- Fund vehicle granularity: distinguish between Fund I, Fund II, etc.
- Co-investor mapping: "which funds co-invest most frequently?"
- Company signals: show signals mentioning a specific portfolio company
- Sector browse page: `/sectors/[sector]` with aggregate views
- CSV/Excel export of filtered company lists
- Company timeline: visual deal history across funds

## 12) Subagent review prompt (use after Sprint plan is drafted)
Paste this to a subagent:

“Review docs/spec.md for: (1) missing critical tickets, (2) over-scoped parts, (3) data model gaps for manager→vehicles complexity, (4) test strategy weaknesses, (5) anything that risks trust/provenance. Suggest improvements as concrete edits + new tickets. Keep it minimal and Italy-first.”

Then incorporate changes and keep docs/spec.md as the single source of truth.
