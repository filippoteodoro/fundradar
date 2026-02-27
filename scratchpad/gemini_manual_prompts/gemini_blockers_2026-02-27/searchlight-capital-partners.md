You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: Searchlight Capital Partners
- slug: searchlight-capital-partners
- website: https://searchlightcap.com
- aum_eur: 14000000000
- category: pe
- hq_city (current db value): New York
- description (current db value): Private equity firm managing approximately USD 15 billion across special situations and buyout strategies. Key Italian investment was EOLO, Italy's leading fixed wireless broadband provider serving 300K+ customers, exited to Partners Group in 2021.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "EOLO",
    "status": "exited",
    "sector": "Technology",
    "headquarters": "Busto Arsizio, Italy",
    "description": "Italy's leading fixed wireless access broadband provider, serving 300K+ customers across 13 regions.",
    "website": "https://www.eolo.it",
    "investment_date": "2018-01-01",
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Fedrigoni",
    "status": "exited",
    "sector": "Industrial Manufacturing",
    "headquarters": "Verona, Italy",
    "description": "Global leader in specialty papers, self-adhesive labels and packaging materials. Co-owned with Bain Capital. Sold to Advent International (2025).",
    "website": "https://fedrigoni.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "EOLO",
    "status": "exited",
    "sector": "Technology",
    "headquarters": "Busto Arsizio, Italy",
    "description": "Italy's leading fixed wireless access broadband provider, serving 300K+ customers across 13 regions.",
    "website": "https://www.eolo.it",
    "investment_date": "2018-01-01",
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Fedrigoni",
    "status": "exited",
    "sector": "Industrial Manufacturing",
    "headquarters": "Verona, Italy",
    "description": "Global leader in specialty papers, self-adhesive labels and packaging materials. Co-owned with Bain Capital. Sold to Advent International (2025).",
    "website": "https://fedrigoni.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  }
]

Existing names list (for duplicate filtering):
["EOLO", "Fedrigoni"]

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
