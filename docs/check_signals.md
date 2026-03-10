# Signal Quality Checklist — Diagnosing & Fixing Issues

## Philosophy: Systemic Fixes Only

**Never fix a signal by editing JSON files directly** unless you're unblocking yourself during debugging. JSON edits only fix past signals — new signals will have the same problem.

Every fix must go into the pipeline code so it applies automatically to every new signal that flows through. The right place depends on the issue type:

| Fix type | Where | Persists? |
|----------|-------|-----------|
| Text cleaning (spacing, casing, boilerplate) | `signal_text_utils.py` | Yes — runs in both filter and enricher |
| Classification (wrong type, wrong fund) | `signal_corrections.py` + `signal_patterns.py` | Yes — shared by filter and enricher |
| Filtering (passing garbage, blocking legit signals) | `filter_signals.py` | Yes — primary quality gate |
| TS-side type display bugs | `signalProcessing.ts` | Yes — applies on every page load / deploy |
| Fund-specific HTML parsing | `strategies/extractors/{fund}.py` | Yes — re-run with `--force-extract` after change |
| Enricher output quality | `enrich_signals_openai.py` system prompt | Yes — next pipeline run |

**Testing after a Python fix**: `cd apps/worker && pytest` must pass. No new test → the fix may be silently wrong.

---

## Quick Diagnosis Commands

```bash
# See all signals currently in the filtered output
python3 -c "import json; d=json.load(open('data/derived/detected_signals_filtered.json')); print(len(d['signals']), 'filtered signals')"

# Find signals of a specific type
python3 -c "
import json
d = json.load(open('data/derived/detected_signals_filtered.json'))
for s in d['signals']:
    if s.get('signal_type') == 'other':
        print(s['id'], '|', s.get('fund_slug','?'), '|', s.get('title','')[:90])
" | head -30

# Check quality scores
python3 -c "
import json
d = json.load(open('data/derived/detected_signals_filtered.json'))
scores = [(s.get('quality_score',0), s.get('signal_type','?'), s.get('title','')[:70]) for s in d['signals']]
for q,t,title in sorted(scores)[:20]:
    print(f'{q:3d} {t:20s} {title}')
"

# Find signals with 'sale' or other specific text patterns
python3 -c "
import json
d = json.load(open('data/derived/detected_signals_enriched.json'))
for s in d.get('signals', []):
    if 'sale of' in (s.get('title','') + s.get('what_changed','')).lower():
        print(s['id'], s.get('signal_type'), s.get('title','')[:100])
"
```

---

## Issue Catalogue

---

### 1. Boilerplate / PR Language

**Symptoms**: Titles starting with "Press release:", "Comunicato stampa:", "Article in Il Sole:", "[Entity] is pleased to announce that", "Dear investor,", "Contents:"

**Where to fix**: `apps/worker/scripts/signal_text_utils.py`
- `LEADING_LABEL_RE` (line ~86) — strips known prefix labels before the colon separator
- `_cdt_strip_datelines_and_navigation()` — strips PR boilerplate mid-text ("is pleased to announce that", "Article in [Publication]:", multi-city datelines, event datelines)

Also: `apps/web/src/lib/signalProcessing.ts`
- `cleanSignalTitle()` — strips "Press release" prefix, date prefixes, newspaper attribution suffixes

**How to add a new pattern** (Python):
```python
# In LEADING_LABEL_RE alternation:
r"(?:news|update|announcement|press\s+release|comunicato\s+stampa|YOUR_NEW_PREFIX)\s*[:\-–—]"

# In _cdt_strip_datelines_and_navigation():
text = re.sub(r"^[^:]{0,120}\bis\s+pleased\s+to\s+announce\s+that\s+", "", text, flags=re.IGNORECASE)
```

**Prefer short and direct**: strip everything before the actual news fact. "Company X acquires Company Y" not "Wise Equity SGR is pleased to announce that it has today completed the acquisition of Company Y."

---

### 2. Words Merged That Should Be Separate

**Symptoms**: "diMarullo" instead of "di Marullo", "withTechNova" instead of "with TechNova", "€200Magreement" instead of "€200M agreement", "per l'investimento inXYZ" etc.

**Root cause**: PDF extraction / HTML scraping artifacts — words concatenated with no space. OCR errors. Currency magnitude letter (`M`, `B`, `K`) fused to the next word.

**Where to fix**: `apps/worker/scripts/signal_text_utils.py`
- `fix_spacing()` function — add a regex substitution:
  ```python
  # Pattern for preposition + capitalized word:
  text = re.sub(r'\b(di|con|per|da|in|su|the|with|of|by|for|from|at|to|and)\b([A-Z])', r'\1 \2', text)
  # Pattern for €XM + following lowercase word:
  text = re.sub(r'(€\d+(?:\.\d+)?[KMBT])([a-z])', r'\1 \2', text)
  ```

Also TypeScript: `apps/web/src/lib/signalProcessing.ts`
- `fixSignalSpacing()` — for TS-side fixes that aren't covered by Python

**Monetary concatenation** specifically: `normalize_monetary_values()` in `signal_text_utils.py` handles `€3.3Mper` → `€3.3M per`. Add cases there.

---

### 3. Words Separated That Should Be Merged (Brand Names)

**Symptoms**: "Team System" instead of "TeamSystem", "Info Cert" instead of "InfoCert", "Gama Life" instead of "GamaLife", "CDP Venture Capi tal" (split mid-word).

**Root cause**: Casing normalization splitting camelCase brand names, or PDF line breaks.

**Where to fix**: `apps/worker/scripts/signal_text_utils.py`
- `fix_spacing()` — add to the brand-name corrections block:
  ```python
  # Exact-match replacements (case-insensitive → canonical form):
  text = re.sub(r'\bTeam\s+System\b', 'TeamSystem', text, flags=re.IGNORECASE)
  text = re.sub(r'\bInfo\s+Cert\b', 'InfoCert', text, flags=re.IGNORECASE)
  ```

Also TypeScript: `apps/web/src/lib/signalProcessing.ts`
- `fixSignalSpacing()` — the `KNOWN_NAME_CORRECTIONS` dict handles CDP VC artifacts like "WSense", "3DNextech", "IDeA Capital". Add brand names here for TS-side fixes.

**Rule of thumb**: Python fix in `fix_spacing()` is preferred (persists in data). TS fix in `fixSignalSpacing()` is a belt-and-suspenders for cases that slip through.

---

### 4. All-Caps Words That Should Not Be

**Symptoms**: "WISE EQUITY ACQUIRES COMPANY" in signal title. Acronyms like "PER INVESTIRE" (Italian all-caps leak). Company names in all caps from fund website.

**Where to fix**: `apps/worker/scripts/signal_text_utils.py`
- `_cdt_normalize_casing()` — detects high-capitalization ratio and applies `.title()` + re-lowercases small words (Of, And, In, etc.)
- `_TITLE_CASE_ACRONYMS` list (~line 200) — restores correct casing for PE/finance acronyms after `.title()` lowercases them (LBO, MBO, LP, GP, VC, PE, IRR, NAV, SaaS, AI, ICT, B2B, B2C, SME)

**How to add a new acronym**:
```python
_TITLE_CASE_ACRONYMS = [..., "YOUR_ACRONYM"]  # e.g. "ESG", "AIF", "UCITS"
```

TypeScript side: `cleanSignalTitle()` in `signalProcessing.ts` also handles ALL CAPS → title case via the `isAllCaps` detection path.

---

### 5. Monetary Formatting Inconsistency

**Expected format**: `€X.XM`, `€XK`, `€X.XB`, `$X.XM`. No spaces between symbol and amount. No trailing zeros beyond one decimal.

**Symptoms**: "€720,000" instead of "€720K", "€ 1.2 million" instead of "€1.2M", "7 m Funding Round" instead of "€7M Funding Round", "€1.200.000" (European notation).

**Where to fix**: `apps/worker/scripts/signal_text_utils.py`
- `normalize_monetary_values()` — all monetary normalization. Current rules:
  - Comma-formatted thousands: `€720,000` → `€720K`, `€1,200,000` → `€1.2M`
  - Millions word form: `€120 milioni` → `€120M`
  - Raw number + "m Funding/Round": `7 m Funding Round` → `€7M Funding Round`
  - Magnitude letter fused to next word: `€200Magreement` → `€200M agreement`

**How to add a new pattern**:
```python
# In normalize_monetary_values(), before the return:
text = re.sub(
    r'(€|\$|£)\s*(\d+(?:\.\d+)?)\s*(?:million[i]?)\b',
    lambda m: f"{m.group(1)}{_fmt_amount(float(m.group(2)) * 1)}M",
    text, flags=re.IGNORECASE
)
```

Also check `deal_amount` field backfill in `filter_signals.py` (`_RE_EXTRACT_AMOUNT`) — this extracts structured deal amount from text when the field is empty.

---

### 6. Italian Words / Untranslated Signals

**Symptoms**: Signal title in Italian, or Italian phrases mixed in English text ("raccoglie €3.3M per rivoluzionare...").

**Root cause**: Translation step (step 3) skipped or failed for this signal. Or signal arrived after filter was run.

**Where to fix**:
1. **Primary**: `translate_signals.py` (pipeline step 3) — translation must run BEFORE filter. NEVER move translation after filter.
2. **Quality gate**: `filter_signals.py` `calculate_quality_score()` — Italian title penalty: if `title_original` is absent AND title has 2+ Italian content words in ≤15-word title → `-30` quality penalty (pushes below 80-point threshold).
3. **Italian content words list**: `_ITALIAN_CONTENT_WORDS` set in `filter_signals.py` — add new Italian words that should never appear in English titles.
4. **Enricher safety net**: `enrich_signals_openai.py` — secondary translation pass for Italian surviving filter.
5. **Garbage summary detection**: `_is_garbage_summary()` in `signal_text_utils.py` — expanded Italian stop-word list catches Italian LLM summaries.

**For individual Italian terms slipping through** (e.g. "raccoglie" in an otherwise English title): add to `_ITALIAN_CONTENT_WORDS` in `filter_signals.py`.

---

### 7. Misclassification — Wrong Signal Type Displayed

**Most common cases**:
- Exit shown as "Other" → safety net in `signalProcessing.ts` `reclassifySignalType()` downgraded it
- Exit shown as "Deal" → `correct_exit()` flipped it for buyer-cue/acquisition language
- People change shown as "Other" → `correct_people_move()` or `other` rescue didn't fire
- Deal shown as "Partnership" → `correct_deal()` agreement check fired incorrectly

**Diagnosis**:
```python
# Check Python classification
cd apps/worker
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from signal_corrections import apply_type_corrections
result = apply_type_corrections(
    'exit_announced',  # input type
    'full signal text here',
    'title text here',
)
print(result)
"
```

**Where to fix (Python)**:
- New type correction rule → `apps/worker/scripts/signal_corrections.py`
  - `apply_universal_demotions()` — fires first for ALL types (events, press reviews)
  - `correct_exit()` — exit_announced corrections
  - `correct_deal()` — deal_announced corrections
  - `correct_people_move()` — people_move corrections
  - `apply_type_corrections()` `other` rescue — rescues over-demoted signals

- New regex pattern → `apps/worker/scripts/signal_patterns.py` (NEVER inline in filter)

**Where to fix (TypeScript)**:
- `reclassifySignalType()` in `signalProcessing.ts` — TS-side safety net
- `RE_EXIT_VERBS` constant (line 14) — canonical exit verb set; updates propagate to all checks using it

**Rule**: Python fix is authoritative. TypeScript fix is belt-and-suspenders. Both must be in sync.

**Exit classification specifically — key patterns**:
- "sale of [company]" → `\bsale\b` now in `RE_EXIT_VERBS` (fixed Mar 2026)
- "agreement for the sale" → stays exit (not partnership) because `_RE_EXIT_VERBS` matches "sale"
- "divestment" → `divest\w+` in `RE_EXIT_VERBS`; safety net now uses `RE_EXIT_VERBS` directly

**Adding a new test** (required for every classification fix):
```python
# In apps/worker/tests/test_signal_classification.py
def test_your_case_description(self):
    result = apply_type_corrections("exit_announced", "full text", "title")
    assert result == "exit_announced"
```

---

### 8. Useless Signals Passing Filters (False Positives)

**Symptoms**: Navigation text, section headers, cookie notices, generic bios, award listings, team page boilerplate appearing as signals.

**Where to fix**: `apps/worker/scripts/filter_signals.py`
- `GARBAGE_PATTERNS` list (~line 133) — add a new compiled regex:
  ```python
  re.compile(r"your_pattern_here", re.IGNORECASE),
  ```
  Examples already there: nav text (`vai al menu`, `back to top`), generic team copy, board financial approval, LinkedIn artifacts.

- `_is_portfolio_extraction_only()` — for bare company-name extractions with no context
- `_is_team_extraction_only()` — for bulk team list extractions
- Quality score penalties in `calculate_quality_score()` — reduce score instead of hard-block when uncertain

Also: `apps/web/src/lib/signalProcessing.ts`
- `isGarbageSignal()` — TypeScript-side garbage detection (secondary defense)

**Important**: The filter threshold is `MIN_QUALITY_SCORE = 80`. Reducing a signal's score to < 80 is equivalent to filtering it. Use score penalties for gradual tuning; use `GARBAGE_PATTERNS` for clear-cut garbage.

---

### 9. Useful Signals Being Filtered Out (False Negatives) — CRITICAL

This is the most important issue. A missed legitimate signal is worse than a false positive.

**Diagnosis**:
```bash
# Check raw signals vs filtered — which ones got dropped?
python3 -c "
import json
raw = {s['id'] for s in json.load(open('data/derived/detected_signals.json')).get('signals',[])}
filt = {s['id'] for s in json.load(open('data/derived/detected_signals_filtered.json'))['signals']}
print(len(raw - filt), 'signals dropped by filter')
"

# Find a specific dropped signal
python3 -c "
import json
d = json.load(open('data/derived/detected_signals.json'))
for s in d.get('signals',[]):
    if 'keyword_in_title' in s.get('title','').lower():
        print('SCORE:', s.get('quality_score'), 'TYPE:', s.get('signal_type'), s.get('title'))
"
```

**Common causes**:

| Cause | Where it happens | Fix |
|-------|-----------------|-----|
| Quality score < 80 | `calculate_quality_score()` in `filter_signals.py` | Add a quality bonus for the pattern, or lower penalty for false positive case |
| Failed Italy relevance check | `_is_italy_relevant()` in `filter_signals.py` | Check `italy_relevant` and `relevance_reasons` fields; fix geo detection |
| Misattributed signal check | `_is_misattributed_signal()` | Signal mentions another fund's name — tighten the misattribution check |
| Caught by `GARBAGE_PATTERNS` | `is_garbage()` | Pattern too broad — narrow it or add a negation |
| Strict noise gate blocked it | `_passes_strict_quality_gates()` | High-score signals (≥90) bypass strict gates — check if signal's score is at 85-89 |
| Ecosystem newsroom check | `_is_misattributed_signal()` | Signal from CDP VC / Itago / Faro Value must contain fund's slug keyword |
| Translation not run | `translate_signals.py` | Italian title → quality penalty → score < 80; fix the translation step |
| Semantic dedup collapsed it | `_semantic_dedup()` in `filter_signals.py` | Two similar signals within 7 days → one dropped; check if dedup is too aggressive |

**Quality score is the lever**: most false negatives have score 70-79. Find the component pulling the score below 80 and either add a positive signal or fix a false penalty.

---

### 10. Wrong Fund Attribution

**Symptoms**: Signal about Fund A appearing on Fund B's page. Signal from an ecosystem newsroom (CDP VC, Itago, Faro Value) appearing without mentioning that fund.

**Where to fix**:

**Python (primary)**:
- `_is_misattributed_signal()` in `filter_signals.py` — checks if signal names a different known fund
- Ecosystem newsroom check — any signal attributed to an `is_ecosystem_newsroom` fund must contain the fund's distinctive slug keyword in title/what_changed, regardless of source domain
- `fund.get("is_ecosystem_newsroom")` flag in `db.json` — add new ecosystem newsroom funds here (no code change needed, just add the flag)

**TypeScript (secondary)**:
- `signalFundTags.ts` `buildFundMentionEntries()` — controls which fund name patterns are used to attribute signals to funds
- `GENERIC_SHORT_BRANDS` set — prevents common nouns (cherry, silver, bridge) from becoming fund-name patterns
- Uniqueness filter — a short first-word pattern is only kept if it maps to exactly one fund

**For a fund whose signals keep appearing on wrong fund's page**: check `GENERIC_SHORT_BRANDS` and whether the fund's first word is also a word in another fund's name.

---

### 11. Signals Not Showing on Website

Multiple independent causes — check in this order:

1. **Score below threshold** (most common): `quality_score < 80` in `detected_signals_filtered.json`. Fix: raise score via bonuses or fix a false penalty.

2. **Dropped by semantic dedup**: Check if a near-duplicate signal exists from the same fund within 7 days. Both Python dedup (composite key) and TypeScript dedup (semantic 40-60% overlap) can drop signals.

3. **Dropped by cross-fund URL dedup**: `_cross_fund_url_dedup()` in filter — same article from same URL matched to multiple funds → only highest quality copy kept. Others get `co_fund_slugs` but are removed from the main list.

4. **Italy-relevance gate**: `italy_relevant=False` — signal was marked non-Italy-relevant. Check `relevance_score` and `relevance_reasons`. Fix: update geo-relevance patterns if the judgment was wrong.

5. **Fund not showing signals at all**: Check that the fund slug in the signal matches `fund_slug` in `db.json`. Check the extractor's URLS dict.

6. **Cached data**: After any pipeline run, restart `pnpm dev` to see changes. Caches have no TTL.

---

### 12. Signal-to-Portfolio Not Working (New Investment Not Added)

**Symptoms**: A deal signal exists in the enriched output, but the portfolio company doesn't appear on the fund's page.

**Diagnosis**:
```bash
cd apps/worker
python3 scripts/signal_to_portfolio.py --dry-run --slugs fund-slug 2>&1 | grep -i "company_name"
```

**Common causes**:

| Cause | Fix |
|-------|-----|
| `target_companies` field empty | Step 8 (enricher) didn't extract target companies — re-run enricher for this fund's signals OR manually add `target_companies` to the enriched signal |
| `italy_relevant=False` on the signal | Signal was marked non-Italy-relevant; update geo-relevance logic or flag |
| Company name blocked by `portfolio_validation` | Name looks like navigation text or is too short — fix the signal's `target_companies` text |
| PEM merge matching failed | Company name in signal doesn't match PEM deal name — check 4-strategy matching in `data.ts` `getPortfolioForFund()` |
| Fund not in organizer slug patterns | For club deals where fund organized but didn't lead — add signal text patterns to `_find_organizer_slugs()` in `signal_to_portfolio.py` |
| Progress state stuck | Check `data/derived/signal_to_portfolio_progress.json` — if signal ID is in `processed_ids` with incomplete state, the reconciliation loop should reprocess it automatically |

**To force reprocessing**: remove the signal's ID from `signal_to_portfolio_progress.json` → next run will reprocess it.

---

### 13. Non-Important Signals Ranked First / Important Signals Last

**Ranking formula** (signals feed only — `/signals` page):
```
importance = quality_score
           + (evidence_score × 4)
           + type_bonus          # exit/deal=15, fundraise_closed=12, fund_launch=10
           + fund_priority        # higher AUM + Italy-focused = higher priority
           + italy_bonus          # +10 if italy_relevant=true
           + (confidence × 10)   # ML confidence
           + amount_bonus         # log-scaled: €1M→0, €10M→10, €100M→20, €1B→30
```

Where to fix (`apps/web/src/app/signals/SignalsFeed.tsx`):
- `getImportanceScore()` — adjust weights
- `SIGNAL_TYPE_IMPORTANCE` in `signalProcessing.ts` — adjust type bonuses

**Note**: Fund detail pages (`/funds/[slug]`) do NOT rank signals — they show in pipeline order. Only `/signals` page has importance ranking.

**Common causes of bad ranking**:
- No `deal_amount` field → no amount bonus → important large deals rank lower. Fix: `deal_amount` backfill in `filter_signals.py` (`_RE_EXTRACT_AMOUNT`).
- Low `quality_score` for high-value signals → see issue 9.
- `italy_relevant=False` on an Italy-relevant signal → missing the +10 Italy bonus.

---

### 14. Context-Free Signals (Only Names, No Context)

**Symptoms**: Signal title is just a company name — "Azienda XYZ" with no verb, no deal language, no people context. Often from portfolio page extractions.

**Where to fix**: `apps/worker/scripts/filter_signals.py`
- `_is_portfolio_extraction_only()` — detects bare company name signals. For `italy_focused` funds with a core deal/exit type, these are given a passing score (`+88`). For others, score is 0.
- Evidence scoring (`_has_entity()`, `_has_amount()`, `_has_deal_keyword()`) — signals with zero evidence score very low.
- Length penalty: `len(summary.strip()) < 35` in `calculate_quality_score()` → `-15` penalty.

**At the extractor level**: if the extractor is emitting company names with no surrounding context, fix the extractor to extract a richer description or use a different extraction strategy. This is a fund-specific fix (`strategies/extractors/{fund}.py`).

---

### 15. People Changes Marked as "Other"

**Symptoms**: Appointment, hire, departure signal displays as "Other" badge instead of "People Move".

**Root cause**: `correct_people_move()` in `signal_corrections.py` or the `other` rescue in `apply_type_corrections()` didn't recognize the transition verb or role language.

**Where to fix**:

Python: `apps/worker/scripts/signal_corrections.py`
- `RE_PEOPLE_TRANSITION_VERBS` in `signal_patterns.py` — add the missing verb
- `correct_people_move()` — add new correction path
- `other` rescue block in `apply_type_corrections()` — office/presence opening → `people_move`

TypeScript: `apps/web/src/lib/signalProcessing.ts`
- `reclassifySignalType()` — people_move detection for TS-side safety net
- `RE_PEOPLE_TRANSITION_VERBS` constant

**Common missing verbs**: check if the departure/appointment verb appears in `RE_PEOPLE_TRANSITION_VERBS` in `signal_patterns.py`. If not, add it there.

---

## Fix Decision Tree

```
Signal looks wrong?
├── Wrong text (spacing, casing, boilerplate)
│   ├── Python fix: signal_text_utils.py → fix_spacing() / normalize_monetary_values()
│   │              / _cdt_normalize_casing() / _cdt_strip_datelines_and_navigation()
│   └── TypeScript fix: signalProcessing.ts → fixSignalSpacing() / cleanSignalTitle()
│
├── Wrong type badge displayed (Other/Deal/Exit confusion)
│   ├── Python fix: signal_corrections.py → correct_exit() / correct_deal() / apply_type_corrections()
│   │              signal_patterns.py → RE_EXIT_VERBS / RE_PEOPLE_TRANSITION_VERBS / etc.
│   └── TypeScript fix: signalProcessing.ts → reclassifySignalType() → RE_EXIT_VERBS constant
│
├── Signal shouldn't be there (useless/garbage)
│   ├── Python fix: filter_signals.py → GARBAGE_PATTERNS list (add regex)
│   └── TypeScript fix: signalProcessing.ts → isGarbageSignal()
│
├── Signal is missing (should be there but isn't)
│   ├── Check quality_score in detected_signals_filtered.json
│   ├── If score < 80: find what's penalizing it → fix that penalty/add bonus
│   ├── If not in filtered at all: check detected_signals.json (raw) first
│   └── If in raw but not filtered: check italy_relevant, misattribution, garbage flags
│
├── Signal on wrong fund's page
│   ├── Python fix: filter_signals.py → _is_misattributed_signal()
│   └── TypeScript fix: signalFundTags.ts → GENERIC_SHORT_BRANDS / buildFundMentionEntries()
│
└── Investment not in portfolio
    ├── Check target_companies in detected_signals_enriched.json for that signal
    ├── If empty: re-run enricher for the fund or manually add target_companies
    └── If present: check signal_to_portfolio_progress.json and re-run pipeline:signals-to-portfolio
```

---

## Where NOT to Fix

- **Editing `detected_signals_filtered.json` or `detected_signals_enriched.json` directly** — one-off patch only. Next pipeline run overwrites it. Only do this when debugging or unblocking a cost-sensitive re-run.
- **Editing `portfolio_items.json` directly** — same caveat. Survives until the next monitor run for that fund.
- **Adding patterns to `filter_signals.py:_reclassify_signal_type()`** — type corrections belong in `signal_corrections.py` so they're shared with the enricher. Adding inline to filter creates pattern drift.

---

## Testing Protocol

After any Python fix:
```bash
cd apps/worker
pytest tests/test_signal_classification.py -v   # For classification changes
pytest tests/test_signal_patterns.py -v          # For pattern changes
pytest tests/ -q                                  # Full suite (686 tests, ~8s)
```

After any TypeScript fix:
```bash
cd /path/to/repo
pnpm typecheck
pnpm test  # Vitest suite
```

After a pipeline fix, run the signal pipeline on a representative fund to verify:
```bash
pnpm pipeline:signals --slugs wise-equity-sgr   # or another affected fund
```

---

## Known Recurring Issues (Mar 2026)

| Issue | Status | Fix Location |
|-------|--------|-------------|
| "sale" noun not recognized as exit verb | **Fixed Mar 2026** | `RE_EXIT_VERBS` in `signal_patterns.py` + `signalProcessing.ts`; safety net now uses `RE_EXIT_VERBS` directly |
| Safety net for exit signals used inline regex missing `divest\w+` | **Fixed Mar 2026** | Safety net refactored to use `RE_EXIT_VERBS.test(text)` |
| Italian title quality penalty | **Fixed Mar 2026** | `calculate_quality_score()` in `filter_signals.py` |
| Ecosystem newsroom misattribution via RSS | **Fixed Mar 2026** | `_is_misattributed_signal()` now applies to ALL sources |
| Non-Italian EU geography defaulting `italy_relevant=True` | **Fixed Mar 2026** | Negative geo downgrade in `filter_signals.py` |
| Fund-launch verb not matching conjugated forms ("launches") | **Fixed Feb 2026** | `_RE_LAUNCH_FUND` / `_RE_FUND_LAUNCH_VERBS` in `signal_patterns.py` |
| TeamSystem split to "Team System" | Pre-existing brand correction needed | `fix_spacing()` in `signal_text_utils.py` |
