You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: Oaktree Capital Management
- slug: oaktree-capital-management
- website: https://www.oaktreecapital.com
- aum_eur: 205000000000
- category: multi_strategy
- hq_city (current db value): Los Angeles
- description (current db value): Global alternative investment firm founded in 1995 with a long track record in private credit, special situations, and private equity. In Italy, it has been active across complex situations and control investments, including FC Internazionale Milano.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "FC Internazionale Milano",
    "status": "current",
    "sector": "Media & Entertainment",
    "headquarters": "Milan, Italy",
    "description": "Italian football club acquired by Oaktree in 2024 following a debt restructuring process.",
    "website": "https://www.inter.it",
    "investment_date": "2024",
    "source_url": "PEM 2024",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "Conbipel",
    "status": "exited",
    "sector": "Retail",
    "headquarters": "Cocconato, Italy",
    "description": "Italian apparel retailer linked to historical Oaktree activity in PEM records.",
    "website": "https://www.conbipel.com",
    "investment_date": "2007",
    "source_url": "PEM 2007",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "Arsenale S.p.A.",
    "status": "current",
    "sector": "Hospitality & Real Estate",
    "headquarters": "Rome",
    "description": "An Italian luxury hospitality group developing high-end hotels and the 'Orient Express La Dolce Vita' luxury train project. Oaktree invested €300 million in 2022.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.hospitalityinvestor.com/investment/oaktree-invests-eu300m-italian-luxury-hospitality-group",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Banca Progetto",
    "status": "current",
    "sector": "Banking",
    "headquarters": "Milan",
    "description": "An Italian digital bank specializing in lending to small and medium-sized enterprises (SMEs) and salary-backed loans. Oaktree acquired a majority stake in 2015.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.privateequitywire.co.uk/bank-of-italy-intervenes-at-oaktree-backed-banca-progetto/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Castello SGR",
    "status": "current",
    "sector": "Real Estate Asset Management",
    "headquarters": "Milan",
    "description": "A leading Italian real estate asset management company. Oaktree acquired a majority stake in 2020 and sold 80% to Anima Holding in 2023, retaining a 20% stake.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.marketscreener.com/quote/stock/ANIMA-HOLDING-S-P-A-16168683/news/Anima-Holding-S-p-A-acquired-80-stake-in-Castello-SGR-Societa-di-Gestione-del-Risparmio-from-funds-m-44374345/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Cebat",
    "status": "current",
    "sector": "Infrastructure & Energy",
    "headquarters": "Rome",
    "description": "A company specialized in the installation and maintenance of electricity distribution lines and public lighting systems. Oaktree acquired 80% in 2019.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.bebeez.eu/en/2019/06/11/oaktree-takes-over-80-of-cebat-a-specialist-in-electricity-distribution-lines/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Costa Edutainment",
    "status": "current",
    "sector": "Leisure & Entertainment",
    "headquarters": "Genoa",
    "description": "The Italian leader in the management of edutainment parks, including the Aquarium of Genoa and various theme parks. Oaktree acquired a 40% stake in 2019.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.oaktreecapital.com/news-and-insights/press-releases/costa-edutainment-and-oaktree-capital-management-announce-strategic-partnership",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "MBE Worldwide",
    "status": "current",
    "sector": "Logistics & Business Services",
    "headquarters": "Milan",
    "description": "A global platform providing shipping, fulfillment, print, and marketing solutions to SMEs and consumers, operating brands like Mail Boxes Etc. Oaktree invested in 2020.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.bebeez.eu/en/2020/01/09/oaktree-pours-100-mln-euros-in-mbe-wolrdwide-the-italian-owner-of-mail-boxes-etc-brand/",
    "data_source": "gemini_missing_asset"
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "FC Internazionale Milano",
    "status": "current",
    "sector": "Media & Entertainment",
    "headquarters": "Milan, Italy",
    "description": "Italian football club acquired by Oaktree in 2024 following a debt restructuring process.",
    "website": "https://www.inter.it",
    "investment_date": "2024",
    "source_url": "PEM 2024",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "Conbipel",
    "status": "exited",
    "sector": "Retail",
    "headquarters": "Cocconato, Italy",
    "description": "Italian apparel retailer linked to historical Oaktree activity in PEM records.",
    "website": "https://www.conbipel.com",
    "investment_date": "2007",
    "source_url": "PEM 2007",
    "data_source": "pem_manual_seed"
  },
  {
    "name": "Arsenale S.p.A.",
    "status": "current",
    "sector": "Hospitality & Real Estate",
    "headquarters": "Rome",
    "description": "An Italian luxury hospitality group developing high-end hotels and the 'Orient Express La Dolce Vita' luxury train project. Oaktree invested €300 million in 2022.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.hospitalityinvestor.com/investment/oaktree-invests-eu300m-italian-luxury-hospitality-group",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Banca Progetto",
    "status": "current",
    "sector": "Banking",
    "headquarters": "Milan",
    "description": "An Italian digital bank specializing in lending to small and medium-sized enterprises (SMEs) and salary-backed loans. Oaktree acquired a majority stake in 2015.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.privateequitywire.co.uk/bank-of-italy-intervenes-at-oaktree-backed-banca-progetto/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Castello SGR",
    "status": "current",
    "sector": "Real Estate Asset Management",
    "headquarters": "Milan",
    "description": "A leading Italian real estate asset management company. Oaktree acquired a majority stake in 2020 and sold 80% to Anima Holding in 2023, retaining a 20% stake.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.marketscreener.com/quote/stock/ANIMA-HOLDING-S-P-A-16168683/news/Anima-Holding-S-p-A-acquired-80-stake-in-Castello-SGR-Societa-di-Gestione-del-Risparmio-from-funds-m-44374345/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Cebat",
    "status": "current",
    "sector": "Infrastructure & Energy",
    "headquarters": "Rome",
    "description": "A company specialized in the installation and maintenance of electricity distribution lines and public lighting systems. Oaktree acquired 80% in 2019.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.bebeez.eu/en/2019/06/11/oaktree-takes-over-80-of-cebat-a-specialist-in-electricity-distribution-lines/",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "Costa Edutainment",
    "status": "current",
    "sector": "Leisure & Entertainment",
    "headquarters": "Genoa",
    "description": "The Italian leader in the management of edutainment parks, including the Aquarium of Genoa and various theme parks. Oaktree acquired a 40% stake in 2019.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.oaktreecapital.com/news-and-insights/press-releases/costa-edutainment-and-oaktree-capital-management-announce-strategic-partnership",
    "data_source": "gemini_missing_asset"
  },
  {
    "name": "MBE Worldwide",
    "status": "current",
    "sector": "Logistics & Business Services",
    "headquarters": "Milan",
    "description": "A global platform providing shipping, fulfillment, print, and marketing solutions to SMEs and consumers, operating brands like Mail Boxes Etc. Oaktree invested in 2020.",
    "website": null,
    "investment_date": null,
    "source_url": "https://www.bebeez.eu/en/2020/01/09/oaktree-pours-100-mln-euros-in-mbe-wolrdwide-the-italian-owner-of-mail-boxes-etc-brand/",
    "data_source": "gemini_missing_asset"
  }
]

Existing names list (for duplicate filtering):
["FC Internazionale Milano", "Conbipel", "Arsenale S.p.A.", "Banca Progetto", "Castello SGR", "Cebat", "Costa Edutainment", "MBE Worldwide"]

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
