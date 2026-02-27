You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: White Bridge Investments
- slug: white-bridge-investments
- website: https://www.whitebridgeinvestments.com
- aum_eur: 900000000
- category: pe
- hq_city (current db value): Milan
- description (current db value): Led by veterans from major international private equity firms, this firm executes buy-and-build strategies in the Italian mid-market, notably consolidating the nutraceutical sector to form the Named Group.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "Named Group",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Italy",
    "description": "Italian supplements and nutraceutical company, ~EUR 800M valuation",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.whitebridgeinvestments.com",
    "data_source": "manual"
  },
  {
    "name": "Cirelli La Collina Biologica",
    "status": "current",
    "sector": "Food & Beverage",
    "headquarters": "Italy",
    "description": "Italian organic wine producer",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.whitebridgeinvestments.com",
    "data_source": "manual"
  },
  {
    "name": "Delta Med",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Italy",
    "description": "Italian medical devices company",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.whitebridgeinvestments.com",
    "data_source": "manual"
  },
  {
    "name": "Campus",
    "status": "current",
    "sector": "Food & Beverage",
    "headquarters": "Italy",
    "description": "Italian functional food company",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.whitebridgeinvestments.com",
    "data_source": "manual"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "Named Group",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Italy",
    "description": "Italian supplements and nutraceutical company, ~EUR 800M valuation",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.whitebridgeinvestments.com",
    "data_source": "manual"
  },
  {
    "name": "Cirelli La Collina Biologica",
    "status": "current",
    "sector": "Food & Beverage",
    "headquarters": "Italy",
    "description": "Italian organic wine producer",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.whitebridgeinvestments.com",
    "data_source": "manual"
  },
  {
    "name": "Delta Med",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Italy",
    "description": "Italian medical devices company",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.whitebridgeinvestments.com",
    "data_source": "manual"
  },
  {
    "name": "Campus",
    "status": "current",
    "sector": "Food & Beverage",
    "headquarters": "Italy",
    "description": "Italian functional food company",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.whitebridgeinvestments.com",
    "data_source": "manual"
  }
]

Existing names list (for duplicate filtering):
["Named Group", "Cirelli La Collina Biologica", "Delta Med", "Campus"]

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
