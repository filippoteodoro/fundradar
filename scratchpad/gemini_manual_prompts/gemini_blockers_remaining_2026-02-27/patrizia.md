You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: PATRIZIA
- slug: patrizia
- website: https://www.patrizia.ag
- aum_eur: 57000000000
- category: infra
- hq_city (current db value): Augsburg
- description (current db value): European investment manager in real assets with dedicated infrastructure strategies. In Italy, it has built a significant smart streetlighting platform through Atlantico, Ottima, and Selettra.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "Atlantico",
    "status": "current",
    "sector": "Water & Utilities",
    "headquarters": "Milan, Italy",
    "description": "Italian smart public lighting and infrastructure platform associated with PATRIZIA investments.",
    "website": "https://www.atlantico.it",
    "investment_date": "2024",
    "source_url": "PEM 2024",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "Greenthesis",
    "status": "current",
    "sector": "Environmental Services",
    "headquarters": "Segrate, Italy",
    "description": "Italian environmental services group referenced in PEM replacement transaction activity.",
    "website": "https://www.greenthesisgroup.com",
    "investment_date": "2024",
    "source_url": "PEM 2024",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "Biomet",
    "status": "current",
    "sector": "Renewable Energy / Bio-LNG",
    "headquarters": "San Rocco al Porto, Italy",
    "description": "A vertically integrated bio-LNG producer that operates one of Europe's largest plants producing biomethane and liquid natural gas from organic waste.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.ipe.com/news/patrizia-infrastructure-acquires-italian-bio-lng-producer-biomet/10060592.article",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "CiviSmart",
    "status": "current",
    "sector": "Smart City / Infrastructure",
    "headquarters": "Milan, Italy",
    "description": "A consolidated platform company launched by PATRIZIA to manage its Italian smart streetlighting and urban digitalization assets, including Ottima, Selettra, and Atlantico.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.smartcitiesworld.net/lighting/patrizia-launches-new-smart-infrastructure-company-10113",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Ecotermica Servizi S.p.A.",
    "status": "current",
    "sector": "Energy / District Heating",
    "headquarters": "Turin, Italy",
    "description": "A developer and operator of cogeneration and district heating networks in the Piedmont and Val d'Aosta regions of Italy.",
    "website": null,
    "investment_date": null,
    "source_url": "https://bebeez.it/en/infrastructure-en/patrizia-infrastructure-and-universal-investment-launch-patrizia-infrastructure-invest-eltif/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Ottima S.r.l.",
    "status": "current",
    "sector": "Smart City / Infrastructure",
    "headquarters": "Milan, Italy",
    "description": "An Italian smart streetlighting company that partners with small to medium-sized municipalities to design, install, and manage connected lighting points and smart city services.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.ipe.com/news/patrizia-acquires-italian-smart-streetlighting-company-ottima/10062514.article",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Renergia",
    "status": "current",
    "sector": "Renewable Energy / Biomethane",
    "headquarters": "Milan, Italy",
    "description": "An integrated renewable fuels platform in Italy focused on converting biogas plants to biomethane production and bio-LNG liquefaction.",
    "website": null,
    "investment_date": null,
    "source_url": "https://lngprime.com/europe/renergia-to-further-grow-italian-bio-lng-business/124798/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Selettra S.r.l.",
    "status": "current",
    "sector": "Smart City / Infrastructure",
    "headquarters": "Potenza, Italy",
    "description": "One of Italy's largest independent smart streetlighting operators, managing over 140,000 light points across multiple regions.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.ipe.com/news/patrizia-buys-italys-second-largest-smart-streetlighting-firm-selettra-for-140m/10063165.article",
    "data_source": "gemini_missing_asset"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "Atlantico",
    "status": "current",
    "sector": "Water & Utilities",
    "headquarters": "Milan, Italy",
    "description": "Italian smart public lighting and infrastructure platform associated with PATRIZIA investments.",
    "website": "https://www.atlantico.it",
    "investment_date": "2024",
    "source_url": "PEM 2024",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "Greenthesis",
    "status": "current",
    "sector": "Environmental Services",
    "headquarters": "Segrate, Italy",
    "description": "Italian environmental services group referenced in PEM replacement transaction activity.",
    "website": "https://www.greenthesisgroup.com",
    "investment_date": "2024",
    "source_url": "PEM 2024",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "Biomet",
    "status": "current",
    "sector": "Renewable Energy / Bio-LNG",
    "headquarters": "San Rocco al Porto, Italy",
    "description": "A vertically integrated bio-LNG producer that operates one of Europe's largest plants producing biomethane and liquid natural gas from organic waste.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.ipe.com/news/patrizia-infrastructure-acquires-italian-bio-lng-producer-biomet/10060592.article",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "CiviSmart",
    "status": "current",
    "sector": "Smart City / Infrastructure",
    "headquarters": "Milan, Italy",
    "description": "A consolidated platform company launched by PATRIZIA to manage its Italian smart streetlighting and urban digitalization assets, including Ottima, Selettra, and Atlantico.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.smartcitiesworld.net/lighting/patrizia-launches-new-smart-infrastructure-company-10113",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Ecotermica Servizi S.p.A.",
    "status": "current",
    "sector": "Energy / District Heating",
    "headquarters": "Turin, Italy",
    "description": "A developer and operator of cogeneration and district heating networks in the Piedmont and Val d'Aosta regions of Italy.",
    "website": null,
    "investment_date": null,
    "source_url": "https://bebeez.it/en/infrastructure-en/patrizia-infrastructure-and-universal-investment-launch-patrizia-infrastructure-invest-eltif/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Ottima S.r.l.",
    "status": "current",
    "sector": "Smart City / Infrastructure",
    "headquarters": "Milan, Italy",
    "description": "An Italian smart streetlighting company that partners with small to medium-sized municipalities to design, install, and manage connected lighting points and smart city services.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.ipe.com/news/patrizia-acquires-italian-smart-streetlighting-company-ottima/10062514.article",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Renergia",
    "status": "current",
    "sector": "Renewable Energy / Biomethane",
    "headquarters": "Milan, Italy",
    "description": "An integrated renewable fuels platform in Italy focused on converting biogas plants to biomethane production and bio-LNG liquefaction.",
    "website": null,
    "investment_date": null,
    "source_url": "https://lngprime.com/europe/renergia-to-further-grow-italian-bio-lng-business/124798/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Selettra S.r.l.",
    "status": "current",
    "sector": "Smart City / Infrastructure",
    "headquarters": "Potenza, Italy",
    "description": "One of Italy's largest independent smart streetlighting operators, managing over 140,000 light points across multiple regions.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.ipe.com/news/patrizia-buys-italys-second-largest-smart-streetlighting-firm-selettra-for-140m/10063165.article",
    "data_source": "gemini_missing_asset"
  }
]

Existing names list (for duplicate filtering):
["Atlantico", "Greenthesis", "Biomet", "CiviSmart", "Ecotermica Servizi S.p.A.", "Ottima S.r.l.", "Renergia", "Selettra S.r.l."]

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
