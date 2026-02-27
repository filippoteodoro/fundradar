You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: ICG
- slug: icg
- website: https://www.icgam.com
- aum_eur: 113000000000
- category: multi_strategy
- hq_city (current db value): London
- description (current db value): FTSE 100-listed global alternative asset manager that pioneered the European mezzanine finance market in 1989, now providing flexible capital solutions across private debt, credit, and real estate.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "BioGroup",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Courbevoie, France",
    "description": "French medical laboratory group where ICG has been reported as an equity owner alongside other institutional investors.",
    "website": "https://www.biogroup-lcd.com",
    "investment_date": null,
    "source_url": "https://www.icgam.com",
    "data_source": "manual"
  },
  {
    "name": "Dümmen Orange",
    "status": "current",
    "sector": "Agriculture",
    "headquarters": "De Lier, Netherlands",
    "description": "International horticulture business in which ICG has been disclosed as part of the lender group that took majority ownership in a 2024 restructuring.",
    "website": "https://www.dummenorange.com",
    "investment_date": "2024-01-01",
    "source_url": "https://www.icgam.com",
    "data_source": "manual"
  },
  {
    "name": "Courtepaille",
    "status": "exited",
    "sector": "Food & Beverage",
    "headquarters": "Paris, France",
    "description": "French restaurant chain previously owned by ICG before its 2020 sale.",
    "website": "https://www.courtepaille.com",
    "investment_date": "2015-01-01",
    "source_url": "https://www.icgam.com",
    "data_source": "manual"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[]

Existing names list (for duplicate filtering):
["BioGroup", "Dümmen Orange", "Courtepaille"]

Task:
1) Audit ONLY the likely Italy-relevant entries subset for wrong entry/duplicate/status/sector/headquarters/description.
2) Find likely MISSING Italian assets (current or exited) not already in existing names.
3) Suggest fund metadata corrections only if likely wrong (hq_city, description, website).
4) If you find no credible Italian asset exposure for this fund, set `confirmed_no_italian_assets=true`.

Rules:
- Be conservative when uncertain and lower confidence.
- Use high confidence only with credible evidence.
- Return ONLY strict JSON object (no markdown).

JSON schema:
{
  "entry_issues": [
    {
      "entry_name": "string",
      "issue_type": "wrong_entry|duplicate_entry|wrong_status|wrong_sector|wrong_headquarters|wrong_description|other",
      "severity": "critical|high|medium|low",
      "reason": "short reason",
      "current_value": {"status": "...", "sector": "...", "headquarters": "...", "description": "..."},
      "suggested_fix": {"status": "current|exited|partial|unknown|null", "sector": "string|null", "headquarters": "string|null", "description": "string|null"},
      "confidence": "high|medium|low",
      "evidence_urls": ["https://..."]
    }
  ],
  "missing_assets": [
    {
      "name": "string",
      "status": "current|exited|unknown",
      "sector": "string|null",
      "headquarters": "string|null",
      "description": "string|null",
      "reason": "why this is likely missing",
      "confidence": "high|medium|low",
      "evidence_urls": ["https://..."]
    }
  ],
  "fund_metadata_corrections": {
    "hq_city": {"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]},
    "description": {"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]},
    "website": {"current": "string|null", "suggested": "string|null", "reason": "string", "confidence": "high|medium|low", "evidence_urls": ["https://..."]}
  },
  "confirmed_no_italian_assets": false,
  "notes": "optional short note"
}
