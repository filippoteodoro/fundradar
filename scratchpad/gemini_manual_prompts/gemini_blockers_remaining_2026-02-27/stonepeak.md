You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: Stonepeak
- slug: stonepeak
- website: https://stonepeak.com
- aum_eur: 77000000000
- category: infra
- hq_city (current db value): New York
- description (current db value): Alternative investment firm focused on infrastructure and real assets globally. Stonepeak has active exposure to Italy through transactions such as Forgital Group and other energy and industrial infrastructure opportunities.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "Forgital",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Velo d'Astico, Italy",
    "description": "Leader in Italy in the camping-village sector, with an integrated business model that combines hospitality offerings with ancillary services (restaurants, bars, swimming pools, equipped beaches)",
    "website": "https://www.forgital.com",
    "investment_date": "2024",
    "source_url": "PEM 2024",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "FiberCop",
    "status": "current",
    "sector": "Telecom Infrastructure",
    "headquarters": "Rome, Italy",
    "description": "Italy's primary fixed-line telecommunications network infrastructure, formerly known as TIM's NetCo.",
    "website": null,
    "investment_date": null,
    "source_url": "https://stonepeak.com/2024/07/kkr-completes-acquisition-of-tims-fixed-network/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "PIR Group (La Petrolifera Italo Rumena)",
    "status": "current",
    "sector": "Energy & Logistics",
    "headquarters": "Ravenna, Italy",
    "description": "An independent terminal operator providing storage and handling services for liquid bulk products in the Mediterranean.",
    "website": null,
    "investment_date": null,
    "source_url": "https://stonepeak.com/2020/10/stonepeak-infrastructure-partners-and-pir-group-announce-strategic-partnership/",
    "data_source": "gemini_missing_asset"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "Forgital",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Velo d'Astico, Italy",
    "description": "Leader in Italy in the camping-village sector, with an integrated business model that combines hospitality offerings with ancillary services (restaurants, bars, swimming pools, equipped beaches)",
    "website": "https://www.forgital.com",
    "investment_date": "2024",
    "source_url": "PEM 2024",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "FiberCop",
    "status": "current",
    "sector": "Telecom Infrastructure",
    "headquarters": "Rome, Italy",
    "description": "Italy's primary fixed-line telecommunications network infrastructure, formerly known as TIM's NetCo.",
    "website": null,
    "investment_date": null,
    "source_url": "https://stonepeak.com/2024/07/kkr-completes-acquisition-of-tims-fixed-network/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "PIR Group (La Petrolifera Italo Rumena)",
    "status": "current",
    "sector": "Energy & Logistics",
    "headquarters": "Ravenna, Italy",
    "description": "An independent terminal operator providing storage and handling services for liquid bulk products in the Mediterranean.",
    "website": null,
    "investment_date": null,
    "source_url": "https://stonepeak.com/2020/10/stonepeak-infrastructure-partners-and-pir-group-announce-strategic-partnership/",
    "data_source": "gemini_missing_asset"
  }
]

Existing names list (for duplicate filtering):
["Forgital", "FiberCop", "PIR Group (La Petrolifera Italo Rumena)"]

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
