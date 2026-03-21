# Portfolio Signal Misclassification Audit Report

**Date:** 2026-02-17  
**Total Signals Found:** 19 signals that should be `portfolio_update` but are currently misclassified

---

## Summary by Current Signal Type

| Current Type | Count |
|--------------|-------|
| `deal_announced` | 9 |
| `partnership` | 7 |
| `other` | 2 |
| `exit_announced` | 1 |
| **TOTAL** | **19** |

---

## Key Patterns

### Why These Should Be `portfolio_update`:

1. **Portfolio company context** - Explicitly mentions "partecipata", "sostenuta da", "portfolio company"
2. **Company operational news** - Revenue targets, expansion plans, product launches
3. **Portfolio company partnerships** - Company making partnerships (not fund-level partnerships)
4. **Portfolio company M&A** - Portfolio company acquiring another company (bolt-on acquisition)
5. **Financial metrics** - Company-level revenue, growth figures

### Key Distinction:
- `deal_announced` = **Fund** investing in NEW company (fund-level deal)
- `portfolio_update` = News about **existing portfolio company** operations
- Example: "NTC backed by Wise Equity completes acquisition" = portfolio company M&A → `portfolio_update`

---

## Detailed Listing (All 19 Signals)

### 1. DEAL_ANNOUNCED → should be PORTFOLIO_UPDATE (9 signals)

#### 1.1 Portfolio Company M&A / Expansion

**ID:** `web-signal-00543`  
**Fund:** `wise-equity-sgr`  
**Title:** NTC sostenuta da Wise Equity, completa l'acquisizione del Business oftalmico di Pharmathen  
**Summary:** NTC backed by Wise Equity, completes acquisition of Pharmathen's Ophthalmic Business.  
**Why:** Explicitly says "sostenuta da" (backed by) + portfolio company completing acquisition  

---

**ID:** `web-signal-01300`  
**Fund:** `fvs-sgr`  
**Title:** Il Gruppo Candy Factory si espande con Italgum Caramelle, storica realtà produttrice di caramelle gommose e gelèes  
**Summary:** THE Candy Factory Group Expands WITH Italgum Caramelle, A Historic Reality Producer OF GUMMY CARAMELS AND GELÉES The Group, promoted by FVS and Hourgl...  
**Why:** "si espande" = company expansion activity (not fund making new investment)  

---

**ID:** `news-signal-20260205111507-934c2dec-95f53995`  
**Fund:** `clessidra-sgr`  
**Title:** Il Gruppo Candy Factory Si Espande con Italgum Caramelle, Storica Realtà Produttrice di Caramelle Gommose E Gelées  
**Summary:** Candy Factory Group Expands with Italgum Caramelle, Historical Manufacturer of Gummies And Gelées.  
**Why:** Same as above - company expansion  

---

**ID:** `seed-signal-00001`  
**Fund:** `kkr`  
**Title:** KKR completes €22 B acquisition of Telecom Italia fixed-line network (Fiber Cop)  
**Summary:** KKR-led consortium completes acquisition of Telecom Italia's fixed-line network, creating Fiber Cop. The deal involves Italian Treasury, F2i, Abu Dhab...  
**Why:** "completes acquisition" - this is about the consortium/portfolio vehicle completing a deal  

---

**ID:** `news-signal-20260205111521-58302957-10b03da7`  
**Fund:** `bc-partners`  
**Title:** Context Logic to Acquire US Salt from Emerald Lake in $907.5 Million Transaction, Creating New Business Ownership Platform in Partnership with Abrams Capital and BC Partners Credit  
**Summary:** Context Logic to Acquire US Salt from Emerald Lake in $907.5 Million Transaction, Creating New Business Ownership Platform in Partnership with Abrams ...  
**Why:** Portfolio company (Context Logic) acquiring another company  

---

#### 1.2 Portfolio Company Capital Raises / Partnerships

**ID:** `news-signal-20260205111509-fb1ed3df-71145585`  
**Fund:** `cdp-venture-capital`  
**Title:** Treccani Futura: aumento di capitale e nuovo piano industriale grazie alla partnership con CDP Venture Capital  
**Summary:** Treccani Futura: capital increase and new business plan thanks to partnership with CDP Venture Capital.  
**Why:** Company news about capital increase (not fund announcing new investment)  

---

**ID:** `web-signal-00837`  
**Fund:** `oakley-capital`  
**Title:** Oakley Capital invests in partnership with luxury clothing and lifestyle brand James Perse  
**Summary:** Oakley Capital invests in partnership with luxury clothing and lifestyle brand James Perse.  
**Why:** Ambiguous - could be fund-level OR portfolio company partnership  

---

**ID:** `news-signal-20260205111507-934c2dec-f5c8f2d2`  
**Fund:** `clessidra-sgr`  
**Title:** Clessidra Private Equity acquisisce Mi CROTEC. Partnership con il fondatore Federico Giudiceandrea, per guidare l'innovazione e la crescita futura  
**Summary:** Hourglass Private Equity acquires Mi CROTEC. Partnership with founder Federico Giudiceandrea to drive innovation and future growth.  
**Why:** Partnership with founder for growth (portfolio company operational news)  

---

**ID:** `web-signal-01037`  
**Fund:** `igi-private-equity`  
**Title:** Igi private equity con il supporto di equiter rileva il controllo di faccin da consilium  
**Summary:** Igi private equity with support from equiter takes over control of faccin from consilium 2.  
**Why:** Has "con il supporto" (with support) indicating portfolio context  

---

### 2. PARTNERSHIP → should be PORTFOLIO_UPDATE (7 signals)

**ID:** `seed-signal-00027`  
**Fund:** `apollo`  
**Title:** Apollo Delos platform commits additional €150 M for Italian special situations  
**Summary:** Apollo strengthened and expanded the Apollo Delos platform (investment partnership with Apeiron Management S.p.A.) with an additional €150 M commitmen...  
**Why:** Platform (portfolio vehicle) getting additional capital  

---

**ID:** `rss-signal-00050`  
**Fund:** `apollo`  
**Title:** Cherry Bank stringe partnership con Apollo e apre ai private markets  
**Summary:** Cherry Bank signs strategic partnership with Apollo Global Management and opens to private markets for Italian clients.  
**Why:** Portfolio company partnership (Cherry Bank is the company, not Apollo making a new deal)  

---

**ID:** `web-signal-01386`  
**Fund:** `wise-equity-sgr`  
**Title:** MEP rafforza la partnership con Promostar  
**Summary:** MEP strengthens partnership with Promostar.  
**Why:** Portfolio company (MEP) partnership news  

---

**ID:** `web-signal-01149`  
**Fund:** `l-catterton`  
**Title:** EX NIHILO Announces Strategic Partnership With L Catterton  
**Summary:** EX NIHILO Announces Strategic Partnership With L Catterton.  
**Why:** Company announcing partnership (could be new investment OR portfolio company news - needs verification)  

---

**ID:** `web-signal-01005`  
**Fund:** `equinox-aifm`  
**Title:** Quid inks an important partnership with Isybank, Intesa Sanpaolo's digital bank  
**Summary:** Quid has signed a partnership agreement with Isybank, Intesa Sanpaolo's digital bank, announced in a dated 2024-04-19; the announcement describes the ...  
**Why:** Portfolio company (Quid) partnership with bank  

---

**ID:** `news-signal-20260205111521-58302957-20c60eee`  
**Fund:** `bc-partners`  
**Title:** Fortidia announces strategic partnership with BC Partners to accelerate global growth  
**Summary:** Fortidia announces strategic partnership with BC Partners to accelerate global growth.  
**Why:** Company partnership announcement (needs verification if new investment or portfolio company)  

---

**ID:** `news-signal-20260205111507-934c2dec-d54a9910`  
**Fund:** `clessidra-sgr`  
**Title:** Human Company: finalizzata la partnership con Hines, affiancata da Apollo, e Clessidra  
**Summary:** Clessidra, alongside Hines and Apollo, finalized a partnership with Human Company on 2026-02-05.  
**Why:** Portfolio company (Human Company) partnership finalized  

---

### 3. OTHER → should be PORTFOLIO_UPDATE (2 signals)

**ID:** `rss-signal-00084`  
**Fund:** `alkemia-sgr`  
**Title:** La insurtech italiana hlpy raggiunge ricavi ricorrenti per circa 60 mln euro nel 2025. Target di oltre 100 mln nei prossimi 24 mesi  
**Summary:** Italian insurtech hlpy expects recurring revenues of about €60 million in 2025 and targets over €100 million within the next 24 months.  
**Why:** Company revenue forecasts and targets (operational news)  

---

**ID:** `rss-signal-00083`  
**Fund:** `nextalia-sgr`  
**Title:** La insurtech italiana hlpy raggiunge ricavi ricorrenti per circa 60 mln euro nel 2025. Target di oltre 100 mln nei prossimi 24 mesi  
**Summary:** Italian insurtech hlpy expects recurring revenues of about €60 million in 2025 and targets over €100 million within the next 24 months.  
**Why:** Same as above - company revenue forecasts (same story tagged to 2 funds)  

---

### 4. EXIT_ANNOUNCED → should be PORTFOLIO_UPDATE (1 signal)

**ID:** `web-signal-01387`  
**Fund:** `wise-equity-sgr`  
**Title:** Il Fondo Wisequity IV cede a NEVERHACK la partecipata Innovery  
**Summary:** Wise Equity Sgr's Wisequity IV fund sold its portfolio company Innovery to NEVERHACK; the transaction was announced in a Wise Equity dated 2026-02-12.  
**Why:** Explicitly mentions "partecipata" (portfolio company) - this IS correctly about a fund exit, but the pattern matched on "partecipata". **NOTE:** This one might be correctly classified as `exit_announced` - needs review.

---

## Next Steps

**DO NOT FIX ANYTHING YET** - this is an audit report only.

### Questions to Resolve:

1. **`exit_announced` signal (web-signal-01387)**: Is this actually correct as `exit_announced`? Or should exits about portfolio companies also be tagged as `portfolio_update`?

2. **Ambiguous partnership signals**: Several signals like "Company announces partnership with Fund" could be either:
   - New fund investment → `deal_announced`
   - Existing portfolio company partnership → `portfolio_update`
   - Need to check if company is already in portfolio

3. **Pattern refinement needed**: The detection patterns are catching many valid cases, but some edge cases need manual review.

### Recommended Actions:

1. Review the enrichment logic in `enrich_signals_openai.py` to better distinguish:
   - Fund-level deals vs portfolio company activity
   - New investments vs portfolio company partnerships
   - Fund exits vs portfolio company operational news

2. Add explicit checks for:
   - "sostenuta da" / "backed by" → portfolio_update
   - "partecipata" / "portfolio company" → portfolio_update
   - Company name + "expands" / "targets" / "launches" → portfolio_update

3. Consider whether `exit_announced` should remain separate or be merged into `portfolio_update` for consistency.
