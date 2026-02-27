You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: VAM Investments
- slug: vam-investments
- website: https://www.vaminvestments.com
- aum_eur: 500000000
- category: pe
- hq_city (current db value): Milan
- description (current db value): Specializes in the consolidation of 'Made in Italy' supply chains under the leadership of luxury veteran Francesco Trapani, notably through the creation of the Gruppo Florence fashion manufacturing platform.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "Everest",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Milan, Italy",
    "description": "Everest is an Italian company specializing in the design, installation, and maintenance of elevators and lifting systems.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Gym Nation Italia",
    "status": "current",
    "sector": "Hospitality & Tourism",
    "headquarters": "Milan, Italy",
    "description": "Gym Nation is a fitness club operator in Italy providing high-quality gym facilities and wellness services.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Etjca Group",
    "status": "current",
    "sector": "Professional Services",
    "headquarters": "Milan, Italy",
    "description": "Etjca is a leading Italian employment agency providing temporary staffing, recruitment, and human resources consultancy services.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Gruppo Florence",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Milano, Italy",
    "description": "An integrated industrial platform for high-end Italian fashion manufacturing, supporting luxury brands globally.",
    "website": "https://www.gruppoflorence.it",
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Soundreef",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Rome, Italy",
    "description": "An independent management entity that audits, collects, and maximizes royalties for authors and publishers.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Supermoney",
    "status": "current",
    "sector": "Financial Services",
    "headquarters": "Milan, Italy",
    "description": "Supermoney is an online comparison platform for insurance, energy, and financial products in the Italian market.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Sicurezza E Ambiente",
    "status": "current",
    "sector": "Environmental Services",
    "headquarters": "Rome, Italy",
    "description": "Sicurezza e Ambiente provides specialized services for the restoration of road safety and environmental conditions following traffic accidents.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Slam",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Genoa, Italy",
    "description": "Slam is an iconic Italian brand specializing in technical apparel and accessories for sailing and nautical sports.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Ssolar",
    "status": "current",
    "sector": "Renewable Energy",
    "headquarters": "Milan, Italy",
    "description": "Ssolar is an investment platform focused on the acquisition and management of photovoltaic plants and renewable energy assets.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "DentalPro",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Milan, Italy",
    "description": "A leading network of dental clinics in Italy.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Conformgest",
    "status": "current",
    "sector": "Financial Services",
    "headquarters": "Biella, Italy",
    "description": "ConformGest S.p.A. è un'azienda specializzata nell'erogazione di garanzie convenzionali di conformità per veicoli usati e nuovi.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Demenego",
    "status": "current",
    "sector": "Professional Services",
    "headquarters": "Calalzo di Cadore, Italy",
    "description": "A specialized optical center chain in Italy, financed by Eurazeo's private debt fund.",
    "website": "https://montefiore.eu/en/portfolio/demenego/",
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "Everest",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Milan, Italy",
    "description": "Everest is an Italian company specializing in the design, installation, and maintenance of elevators and lifting systems.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Gym Nation Italia",
    "status": "current",
    "sector": "Hospitality & Tourism",
    "headquarters": "Milan, Italy",
    "description": "Gym Nation is a fitness club operator in Italy providing high-quality gym facilities and wellness services.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Etjca Group",
    "status": "current",
    "sector": "Professional Services",
    "headquarters": "Milan, Italy",
    "description": "Etjca is a leading Italian employment agency providing temporary staffing, recruitment, and human resources consultancy services.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Gruppo Florence",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Milano, Italy",
    "description": "An integrated industrial platform for high-end Italian fashion manufacturing, supporting luxury brands globally.",
    "website": "https://www.gruppoflorence.it",
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Soundreef",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Rome, Italy",
    "description": "An independent management entity that audits, collects, and maximizes royalties for authors and publishers.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Supermoney",
    "status": "current",
    "sector": "Financial Services",
    "headquarters": "Milan, Italy",
    "description": "Supermoney is an online comparison platform for insurance, energy, and financial products in the Italian market.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Sicurezza E Ambiente",
    "status": "current",
    "sector": "Environmental Services",
    "headquarters": "Rome, Italy",
    "description": "Sicurezza e Ambiente provides specialized services for the restoration of road safety and environmental conditions following traffic accidents.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Slam",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Genoa, Italy",
    "description": "Slam is an iconic Italian brand specializing in technical apparel and accessories for sailing and nautical sports.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Ssolar",
    "status": "current",
    "sector": "Renewable Energy",
    "headquarters": "Milan, Italy",
    "description": "Ssolar is an investment platform focused on the acquisition and management of photovoltaic plants and renewable energy assets.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "DentalPro",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Milan, Italy",
    "description": "A leading network of dental clinics in Italy.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Conformgest",
    "status": "current",
    "sector": "Financial Services",
    "headquarters": "Biella, Italy",
    "description": "ConformGest S.p.A. è un'azienda specializzata nell'erogazione di garanzie convenzionali di conformità per veicoli usati e nuovi.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  },
  {
    "name": "Demenego",
    "status": "current",
    "sector": "Professional Services",
    "headquarters": "Calalzo di Cadore, Italy",
    "description": "A specialized optical center chain in Italy, financed by Eurazeo's private debt fund.",
    "website": "https://montefiore.eu/en/portfolio/demenego/",
    "investment_date": null,
    "source_url": "https://www.vaminvestments.com/en/portfolio-en/",
    "data_source": "fund_website"
  }
]

Existing names list (for duplicate filtering):
["Everest", "Gym Nation Italia", "Etjca Group", "Gruppo Florence", "Soundreef", "Supermoney", "Sicurezza E Ambiente", "Slam", "Ssolar", "DentalPro", "Conformgest", "Demenego"]

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
