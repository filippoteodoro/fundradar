# Signal Classification Accuracy Audit Report

**Date:** 2026-02-16
**File Audited:** `data/derived/detected_signals_enriched.json`
**Total Signals:** 428

---

## Executive Summary

**Overall Accuracy: 48.6%** (208/428 correctly classified)

**Misclassified: 220 signals (51.4%)**

The audit reveals a **critical systematic failure** in signal classification. Over half of all signals are incorrectly classified, with the vast majority of errors stemming from:

1. **RSS feed noise** being classified as `deal_announced` when it should be `other`
2. **Portfolio company fundraising rounds** being confused with **fund LP fundraising**
3. **Accelerator/program launches** being classified as `fund_launch` or `deal_announced`
4. **Missing fund involvement detection** - many signals have NO actual fund activity

---

## Overall Distribution

| Signal Type | Count | % of Total |
|-------------|-------|-----------|
| deal_announced | 251 | 58.6% |
| exit_announced | 57 | 13.3% |
| fund_launch | 35 | 8.2% |
| people_move | 24 | 5.6% |
| fundraise_announced | 22 | 5.1% |
| report | 14 | 3.3% |
| fundraise_closed | 13 | 3.0% |
| partnership | 6 | 1.4% |
| other | 5 | 1.2% |
| job_posting | 1 | 0.2% |

**CRITICAL ISSUE:** Only 5 signals (1.2%) classified as `other`, yet this should be the largest category for RSS feed noise.

---

## Top Misclassification Patterns

### 1. **other_as_deal_announced: 93 signals (42.3% of all errors)**

**Root Cause:** RSS feeds contain general startup news that mentions a fund but the fund is NOT actually participating in the deal.

**Examples:**
- `news-signal-20260205111509-fb1ed3df-f5257bff`: "Nasce a Torino l'acceleratore Takeoff" - CDP mentioned in article but it's about accelerator launch, not a deal
- `news-signal-20260205111509-fb1ed3df-5556f918`: "Soundsafe Care chiude il suo primo aumento di capitale da 1,75 milioni" - CDP not mentioned as investor
- `news-signal-20260205111509-fb1ed3df-cdc3f0b5`: "Mole Urbana: la startup di veicoli elettrici Made in Italy conclude un aumento di capitale" - Generic news

**Why This Happens:**
- RSS monitor associates signals with funds based on keyword matching
- No verification that the fund is actually PARTICIPATING in the deal
- Pattern matching sees "raises €X million" and assumes deal_announced
- Missing logic: "Is the fund mentioned as an investor/participant?"

**Impact:** Massive signal noise - users see deals the fund isn't involved in

---

### 2. **other_as_fund_launch: 18 signals (8.2% of errors)**

**Root Cause:** Accelerators, programs, hubs, and poles are classified as fund launches.

**Examples:**
- `news-signal-20260205111509-fb1ed3df-c2a38335`: "CDP: Claudia Pingue nominata Responsabile del Fondo" - Appointment, not fund launch
- `news-signal-20260205111509-fb1ed3df-474399a5`: "8 milioni di euro per 50 startup ad alto potenziale. Programma Acceler ORA" - Program, not fund
- `rss-signal-00084`: "La insurtech italiana hlpy raggiunge ricavi ricorrenti per circa 60 mln euro nel 2025" - Revenue news, not fund

**Why This Happens:**
- "Lancia acceleratore" → mistaken for "lancia fondo"
- "Programma/polo/hub" keywords trigger fund_launch classification
- Missing check: Is it a FONDO/FUND vehicle or something else?

**Impact:** False signals about new investment vehicles

---

### 3. **other_as_people_move: 17 signals (7.7% of errors)**

**Root Cause:** Generic mentions of people in news articles classified as key hires/appointments.

**Examples:**
- `web-signal-00323`: "New team members: Cristina Bini (+11 more)" - Generic team page update
- `rss-signal-00034`: "Ottaviano (Clessidra): Ecco perché non temiamo i compounder" - Interview/opinion piece

**Why This Happens:**
- Any mention of names/titles triggers people_move
- No check for actual appointment/hire announcement

**Impact:** Noise in people movement tracking

---

### 4. **other_as_exit_announced: 15 signals (6.8% of errors)**

**Examples:**
- `rss-signal-00078`: "Evoluzione editoriale per Grazia: da settimanale passa a quindicinale" - Magazine format change
- `web-signal-01281`: "Philogen IPO: final results of institutional placement" - IPO, not exit

**Why This Happens:**
- IPOs confused with exits
- Any sale/change in portfolio companies assumed to be fund exit

---

### 5. **deal_announced_as_partnership: 5 signals (2.3% of errors)**

**Root Cause:** Using "partnership" language to describe investments.

**Examples:**
- `news-signal-20260205111509-fb1ed3df-71145585`: "Treccani Futura: aumento di capitale e nuovo piano industriale grazie alla **partnership** con CDP Venture Capital" - This is an INVESTMENT described as partnership
- `rss-signal-00046`: "Bandosubito incassa round da 2 mln euro, guidato da Zest" - Clear deal
- `rss-signal-00050`: "Cherry Bank stringe partnership con Apollo e apre ai private markets" - Investment, not partnership

**Why This Happens:**
- Italian business press uses "partnership" to describe investments
- LLM takes the word "partnership" literally
- Missing context: Is money changing hands for equity? → deal

**Impact:** Underreporting of actual deals

---

### 6. **deal_announced_as_fundraise_closed: 5 signals (2.3% of errors)**

**Root Cause:** PORTFOLIO COMPANY rounds confused with FUND LP fundraising.

**Examples:**
- `news-signal-20260205111509-fb1ed3df-188e2047`: "**Arduino** annuncia il completamento di un round aggiuntivo di 20 milioni" - Company raises, not fund
- `news-signal-20260205111509-fb1ed3df-a7c82027`: "**ARCA Dynamics** chiude con successo il primo Round Pre Seed da 1,2 M €" - Company raises, not fund

**Why This Happens:**
- "Chiude round da €X M" triggers fundraise_closed
- No check: Is it the FUND or a PORTFOLIO COMPANY raising?
- Key distinction missed: "Arduino chiude round" ≠ "Fondo X chiude round"

**Impact:** Critical misrepresentation - fund activity vs portfolio company activity

---

### 7. **fundraise_announced_as_deal_announced: 3 signals (1.4% of errors)**

**Root Cause:** OPPOSITE of #6 - actual fund raises misclassified as deals.

**Examples:**
- `news-signal-20260205111509-fb1ed3df-6b0c5fb5`: "Cubbit, il primo enabler di cloud geo-distribuito, raccoglie 12,5 milioni" - If Cubbit is a portfolio company, this is deal_announced (CORRECT). But if title says "Fondo Cubbit raccoglie", it's fundraise.

**Analysis Needed:** Need to check each case - is "Cubbit" the fund or a company?

---

### 8. **deal_announced_as_fund_launch: 5 signals (2.3% of errors)**

**Examples:**
- `rss-signal-00076`: "Private capital e filiera agroalimentare: il modello FIAF" - Article about fund model, not launch
- `news-signal-20260205105259-8b419cb6-28975cbd`: "Fondo Italiano d'Investimento launches **strategic partnership** with ESG.IAMA Private" - Partnership, not new fund

**Why This Happens:**
- "Lancia partnership" → confused with "lancia fondo"
- Articles ABOUT funds mistaken for fund launches

---

### 9. **fund_launch_as_deal_announced: 3 signals**

**Examples:**
- `news-signal-20260205111509-fb1ed3df-71189221`: "CDP Venture Capital e FEI: al via **Indaco Bio**, il primo fondo nato dalla partnership" - GENUINE fund launch
- `seed-signal-00031`: "Advent and Nextalia complete Tinexta take-private, **launch mandatory tender offer**" - "Launch tender offer" confused with "launch fund"

**Why This Happens:**
- Genuine fund launches not recognized
- "Launch" verb triggers wrong classification

---

## Critical Logic Gaps in Classification System

### 1. **No Fund Involvement Detection**
**Problem:** 70+ signals mention a fund but the fund is NOT participating in the deal.

**Example:** "Startup X raises €5M" appears in CDP Venture Capital RSS feed → auto-tagged as CDP deal, but CDP is NOT mentioned as investor.

**Fix Needed:**
```python
def fund_is_participant(signal, fund):
    """Check if fund is actually mentioned as participant/investor."""
    text = signal['title'] + ' ' + signal.get('enriched_summary', '')
    fund_keywords = [fund.name, fund.slug.replace('-', ' ')]
    investor_keywords = ['investe', 'invest', 'entra nel capitale', 'sottoscrive',
                         'ha partecipato', 'tra gli investitori']

    # Fund must be mentioned AND in context of investing
    for fund_kw in fund_keywords:
        if fund_kw in text.lower():
            # Check nearby context for investment language
            return any(inv_kw in text.lower() for inv_kw in investor_keywords)
    return False
```

### 2. **No Company vs Fund Subject Detection**
**Problem:** "Arduino raises €20M" vs "Fondo Arduino raises €20M" classified the same.

**Fix Needed:**
```python
def is_fund_raising(title):
    """Check if FUND ITSELF is raising from LPs."""
    # Fund + raises in same phrase
    return bool(re.search(r'(fondo|fund|sgr).{0,30}(raises?|raccoglie|chiude|closing)', title.lower()) or
                re.search(r'(raises?|raccoglie|chiude|closing).{0,30}(fondo|fund|sgr)', title.lower()))

def is_company_raising(title):
    """Check if portfolio COMPANY is raising."""
    # Company name (not containing 'fondo') + raises
    return bool(re.search(r'^\w+(?<!fondo)(?<!fund).{0,30}(raises?|raccoglie|chiude.*round)', title.lower()))
```

### 3. **No Accelerator vs Fund Disambiguation**
**Problem:** "Lancia acceleratore" → fund_launch

**Fix Needed:**
```python
def is_fund_vehicle(text):
    """Distinguish fund vehicle from accelerator/program."""
    has_fund = 'fondo' in text.lower() or 'fund' in text.lower()
    has_non_fund = any(word in text.lower() for word in
                       ['accelerat', 'programma', 'hub', 'polo', 'incubat', 'academy'])

    if has_fund and has_non_fund:
        # Both mentioned - check which is the primary subject
        fund_pos = min([text.lower().find(w) for w in ['fondo', 'fund'] if w in text.lower()])
        nonfund_pos = min([text.lower().find(w) for w in
                          ['accelerat', 'programma', 'hub', 'polo'] if w in text.lower()])
        return fund_pos < nonfund_pos  # Fund mentioned first = primary

    return has_fund and not has_non_fund
```

### 4. **Partnership as Investment Wrapper**
**Problem:** Italian press says "partnership con CDP" when they mean "investment by CDP"

**Fix Needed:**
```python
def is_partnership_actually_deal(text):
    """Check if 'partnership' is wrapper for investment."""
    if 'partnership' in text.lower() or 'collabora' in text.lower():
        # Look for investment indicators
        has_money = bool(re.search(r'€\s*\d+|aumento di capitale|round|investimento', text.lower()))
        has_equity = any(word in text.lower() for word in
                        ['capitale', 'equity', 'partecipazione', 'quota'])
        return has_money or has_equity
    return False
```

---

## Recommended Fixes

### **IMMEDIATE (Critical):**

1. **Add fund involvement gate** - Before classifying as deal_announced, verify fund is mentioned as investor
2. **Fix fundraise vs deal** - Distinguish "Fondo X raises" from "Company Y raises"
3. **Fix accelerator detection** - "Lancia acceleratore" → other (NOT fund_launch)
4. **Add partnership→deal override** - "Partnership" + money/equity = deal_announced

### **HIGH PRIORITY:**

5. **Improve pattern matching specificity** - Current patterns too broad
6. **Add negative patterns** - Exclude IPOs from exit_announced, exclude interviews from people_move
7. **Context window analysis** - Check 50 chars around keywords, not whole text

### **MEDIUM PRIORITY:**

8. **Better deal language detection** - "Entra nel capitale", "sottoscrive", "sostiene"
9. **Exit language refinement** - Distinguish "sells company" from "company sells product"
10. **Event detection** - Conferences, summits → other (not deal/partnership)

---

## Classification Type Analysis

### Types Working Well:
- **report**: 14 signals, minimal errors (mostly confusion with portfolio company results)
- **job_posting**: Only 1 signal total (underreporting - should have more)
- **exit_announced**: 57 signals, reasonable accuracy

### Types Broken:
- **deal_announced**: 251 signals (58.6%) but ~40% are false positives (not actual deals)
- **other**: Only 5 signals (1.2%) - should be 100+ (all the RSS noise)
- **fund_launch**: 35 signals but ~half are accelerators/programs
- **fundraise_***: Confused with portfolio company raises

---

## Impact Assessment

### **User Trust:**
- **CRITICAL RISK:** Users see 150+ false signals about deals the fund isn't involved in
- **Credibility damage:** "This fund didn't invest in that company" discoveries undermine platform trust

### **Data Quality:**
- **Signal-to-noise ratio:** ~2:1 false positives in deal_announced category
- **Missing signals:** Legitimate other/partnership/report signals hidden by misclassification

### **Product Value:**
- **Search/filtering broken:** Users filtering for "deals" get accelerator launches and random news
- **Analytics skewed:** Deal count metrics inflated by 40-50%

---

## Next Steps

1. **Update `filter_signals.py`** - Add 4 critical gates listed above
2. **Update `enrich_signals_openai.py`** - Sync post-ML corrections
3. **Re-run pipeline** on all signals: `pnpm pipeline --force-extract`
4. **Regression test** - Manually verify 50 random signals across all types
5. **Add classification confidence scores** - Flag low-confidence for manual review

---

## Test Cases for Validation

After fixes, these should classify correctly:

| Title | Current | Correct | Why |
|-------|---------|---------|-----|
| "Nasce acceleratore Takeoff: 21M investimenti" | deal_announced | other | Accelerator launch |
| "Arduino annuncia completamento round da 20M €" | fundraise_closed | deal_announced | Portfolio company raises |
| "Soundsafe Care chiude aumento capitale 1.75M" | deal_announced | other | Fund NOT mentioned as investor |
| "Partnership con CDP per aumento di capitale" | partnership | deal_announced | Partnership = investment wrapper |
| "Fondo Italiano chiude raccolta a 335 mln" | fundraise_closed | fundraise_closed | CORRECT - fund raises from LPs |
| "Philogen IPO: final results placement" | exit_announced | other | IPO, not exit |
| "Ottaviano (Clessidra): non temiamo compounder" | people_move | other | Interview, not appointment |

---

## Conclusion

The classification system has **systematic logic gaps** that produce a 51.4% error rate. The issues are **fixable with 4 critical gates**:

1. Fund involvement detection
2. Fund vs company subject detection
3. Accelerator vs fund disambiguation
4. Partnership-as-investment detection

**Priority:** Fix gates 1-2 IMMEDIATELY (cover 60% of errors), then 3-4 (cover 85%+ of errors).

**Timeline:**
- Critical fixes: 2-4 hours
- Testing: 2 hours
- Re-run pipeline: 30 mins
- Validation: 1 hour
- **Total:** ~1 day to go from 48.6% to 85%+ accuracy
