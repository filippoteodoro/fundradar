You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: Varde Partners
- slug: varde-partners
- website: https://varde.com
- aum_eur: 15000000000
- category: debt
- hq_city (current db value): Minneapolis
- description (current db value): Spun out of Cargill’s financial markets group in 1993, this global credit specialist targets deep-value opportunities in distressed debt and illiquid assets, focusing on financial services and real estate restructurings.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "Guber Banca",
    "status": "current",
    "sector": "Financial Services",
    "headquarters": "Brescia, Italy",
    "description": "Italian NPL servicer and special situations bank. Varde holds a 33.3% stake since 2018.",
    "website": "https://www.guberbanca.it",
    "investment_date": "2018",
    "source_url": null,
    "data_source": "manual"
  },
  {
    "name": "Borio Mangiarotti",
    "status": "current",
    "sector": "Real Estate",
    "headquarters": "Milan, Italy",
    "description": "Milan-based real estate developer. Varde holds a 20% stake since 2024, partnering on the SEIMILANO urban regeneration project.",
    "website": "https://www.boriomangiarotti.it",
    "investment_date": "2024",
    "source_url": null,
    "data_source": "manual"
  },
  {
    "name": "Boscolo Hotels / Dedica Anthology",
    "status": "exited",
    "sector": "Hospitality & Tourism",
    "headquarters": "Italy",
    "description": "Italian luxury hotel portfolio acquired in 2017 and sold to Covivio in 2021 for approximately EUR 573M.",
    "website": null,
    "investment_date": "2017",
    "source_url": null,
    "data_source": "manual"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "Guber Banca",
    "status": "current",
    "sector": "Financial Services",
    "headquarters": "Brescia, Italy",
    "description": "Italian NPL servicer and special situations bank. Varde holds a 33.3% stake since 2018.",
    "website": "https://www.guberbanca.it",
    "investment_date": "2018",
    "source_url": null,
    "data_source": "manual"
  },
  {
    "name": "Borio Mangiarotti",
    "status": "current",
    "sector": "Real Estate",
    "headquarters": "Milan, Italy",
    "description": "Milan-based real estate developer. Varde holds a 20% stake since 2024, partnering on the SEIMILANO urban regeneration project.",
    "website": "https://www.boriomangiarotti.it",
    "investment_date": "2024",
    "source_url": null,
    "data_source": "manual"
  },
  {
    "name": "Boscolo Hotels / Dedica Anthology",
    "status": "exited",
    "sector": "Hospitality & Tourism",
    "headquarters": "Italy",
    "description": "Italian luxury hotel portfolio acquired in 2017 and sold to Covivio in 2021 for approximately EUR 573M.",
    "website": null,
    "investment_date": "2017",
    "source_url": null,
    "data_source": "manual"
  }
]

Existing names list (for duplicate filtering):
["Guber Banca", "Borio Mangiarotti", "Boscolo Hotels / Dedica Anthology"]

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
