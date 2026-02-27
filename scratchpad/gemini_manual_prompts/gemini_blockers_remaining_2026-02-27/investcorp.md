You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: Investcorp
- slug: investcorp
- website: https://www.investcorp.com
- aum_eur: 55000000000
- category: multi_strategy
- hq_city (current db value): Manama
- description (current db value): Established in 1982 to bridge Gulf capital with Western markets, this manager is recognized for its historic turnarounds of luxury icons Tiffany & Co. and Gucci while operating a global multi-asset platform.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "CloudCare",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Rome, Italy",
    "description": "Italian cloud services and managed IT provider acquired by Investcorp in 2021.",
    "website": "https://www.cloudcare.it",
    "investment_date": "2021-06-01",
    "source_url": "https://www.investcorp.com",
    "data_source": "manual"
  },
  {
    "name": "Corneliani",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Mantova, Italy",
    "description": "Italian menswear brand in the premium and luxury segment, backed by Investcorp after a restructuring transaction.",
    "website": "https://www.corneliani.com",
    "investment_date": null,
    "source_url": "https://www.investcorp.com",
    "data_source": "manual"
  },
  {
    "name": "Vivaticket",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Bologna, Italy",
    "description": "Ticketing and event-access technology platform serving sports, museums, and entertainment venues.",
    "website": "https://www.vivaticket.com",
    "investment_date": null,
    "source_url": "https://www.investcorp.com",
    "data_source": "manual"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "CloudCare",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Rome, Italy",
    "description": "Italian cloud services and managed IT provider acquired by Investcorp in 2021.",
    "website": "https://www.cloudcare.it",
    "investment_date": "2021-06-01",
    "source_url": "https://www.investcorp.com",
    "data_source": "manual"
  },
  {
    "name": "Corneliani",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Mantova, Italy",
    "description": "Italian menswear brand in the premium and luxury segment, backed by Investcorp after a restructuring transaction.",
    "website": "https://www.corneliani.com",
    "investment_date": null,
    "source_url": "https://www.investcorp.com",
    "data_source": "manual"
  },
  {
    "name": "Vivaticket",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Bologna, Italy",
    "description": "Ticketing and event-access technology platform serving sports, museums, and entertainment venues.",
    "website": "https://www.vivaticket.com",
    "investment_date": null,
    "source_url": "https://www.investcorp.com",
    "data_source": "manual"
  }
]

Existing names list (for duplicate filtering):
["CloudCare", "Corneliani", "Vivaticket"]

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
