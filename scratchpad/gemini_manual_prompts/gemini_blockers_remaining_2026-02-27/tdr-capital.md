You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: TDR Capital
- slug: tdr-capital
- website: https://www.tdrcapital.com
- aum_eur: 15000000000
- category: pe
- hq_city (current db value): London
- description (current db value): London-based private equity firm managing EUR 15 billion+ focused on European mid-market buyouts. In Italy, acquired Acqua & Sapone (830+ stores, Italy's leading non-food value retailer) from H.I.G. Capital in 2024 for EUR 1.3 billion.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "Acqua & Sapone",
    "status": "current",
    "sector": "Retail",
    "headquarters": "Civitavecchia, Italy",
    "description": "Established in 1992, Acqua & Sapone is Italy’s leading non-food discount retailer selling a wide range of household and cosmetic products.",
    "website": "https://www.acquaesapone.it",
    "investment_date": "2024-06-25",
    "source_url": null,
    "data_source": null
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "Acqua & Sapone",
    "status": "current",
    "sector": "Retail",
    "headquarters": "Civitavecchia, Italy",
    "description": "Established in 1992, Acqua & Sapone is Italy’s leading non-food discount retailer selling a wide range of household and cosmetic products.",
    "website": "https://www.acquaesapone.it",
    "investment_date": "2024-06-25",
    "source_url": null,
    "data_source": null
  }
]

Existing names list (for duplicate filtering):
["Acqua & Sapone"]

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
