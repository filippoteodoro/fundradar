You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: Cherry Bay Capital
- slug: cherry-bay-capital
- website: https://cherrybaycapital.com
- aum_eur: 100000000
- category: pe
- hq_city (current db value): Milan
- description (current db value): Private investment office and club deal platform founded in Monaco in 2018, connecting Italian family assets to exclusive minority expansion opportunities in high-growth companies such as Bending Spoons and aerospace specialist Poggipolini.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "Poggipolini",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Italy",
    "description": "Leader in precision machining. SIMEST €5M investment enabled acquisition of US company Houston Precision Fasteners for aerospace and defense expansion.",
    "website": "https://www.poggipolini.it",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Tecnomatic",
    "status": "current",
    "sector": "Automotive",
    "headquarters": "Corropoli, Italy",
    "description": "engineering and production of hairpin technology automated lines for electric motors, as well as testing and assembling manufacturing",
    "website": "https://www.tecnomatic.it",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "AWP",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Milan, Italy",
    "description": "leader in research, development and production of advanced phytomolecules for feed and pet animal health solutions",
    "website": "https://www.awpint.com",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Limolane",
    "status": "current",
    "sector": "Software",
    "headquarters": "Milan, Italy",
    "description": "global player for chauffeur premium mobility through a digital software for enterprise clients managing a global community of drivers",
    "website": "https://www.limolane.com",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "M.dot M",
    "status": "current",
    "sector": "Financial Services",
    "headquarters": "London, United Kingdom",
    "description": "Artificial intelligence asset management platform, provider of investment solutions for leading global banks and financial institutions",
    "website": "https://www.mdotm.ai",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Bending Spoons",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Milano, Italy",
    "description": "Founded in 2013 in Copenhagen by four young entrepreneurs and headquartered in Milan, Bending Spoons is a data-driven and data-centric digital company specialized in the acquisition, development and monetization of mobile apps, mainly on Apple’s platform iOS. ",
    "website": "https://bendingspoons.com",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Kampos",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Milan, Italy",
    "description": "luxury sustainable fashion brand mainly focused on beachwear apparel and direct stores in the top luxury turism locations",
    "website": "https://www.kampos.com",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Cutiss",
    "status": "current",
    "sector": "Biotech & Pharma",
    "headquarters": "Zurich, Switzerland",
    "description": "Swiss biotech company focusing on innovation of bio regenerative skin medicine",
    "website": "https://www.cutiss.swiss",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "Poggipolini",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Italy",
    "description": "Leader in precision machining. SIMEST €5M investment enabled acquisition of US company Houston Precision Fasteners for aerospace and defense expansion.",
    "website": "https://www.poggipolini.it",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Tecnomatic",
    "status": "current",
    "sector": "Automotive",
    "headquarters": "Corropoli, Italy",
    "description": "engineering and production of hairpin technology automated lines for electric motors, as well as testing and assembling manufacturing",
    "website": "https://www.tecnomatic.it",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "AWP",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Milan, Italy",
    "description": "leader in research, development and production of advanced phytomolecules for feed and pet animal health solutions",
    "website": "https://www.awpint.com",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Limolane",
    "status": "current",
    "sector": "Software",
    "headquarters": "Milan, Italy",
    "description": "global player for chauffeur premium mobility through a digital software for enterprise clients managing a global community of drivers",
    "website": "https://www.limolane.com",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Bending Spoons",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Milano, Italy",
    "description": "Founded in 2013 in Copenhagen by four young entrepreneurs and headquartered in Milan, Bending Spoons is a data-driven and data-centric digital company specialized in the acquisition, development and monetization of mobile apps, mainly on Apple’s platform iOS. ",
    "website": "https://bendingspoons.com",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  },
  {
    "name": "Kampos",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Milan, Italy",
    "description": "luxury sustainable fashion brand mainly focused on beachwear apparel and direct stores in the top luxury turism locations",
    "website": "https://www.kampos.com",
    "investment_date": null,
    "source_url": "https://cherrybaycapital.com/cherries/",
    "data_source": "fund_website"
  }
]

Existing names list (for duplicate filtering):
["Poggipolini", "Tecnomatic", "AWP", "Limolane", "M.dot M", "Bending Spoons", "Kampos", "Cutiss"]

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
