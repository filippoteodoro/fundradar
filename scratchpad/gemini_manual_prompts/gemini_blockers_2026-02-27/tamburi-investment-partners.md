You are auditing portfolio data quality for an Italy-focused PE/VC intelligence product.

Fund:
- name: Tamburi Investment Partners
- slug: tamburi-investment-partners
- website: https://www.tipspa.it
- aum_eur: 5000000000
- category: pe
- hq_city (current db value): Milan
- description (current db value): Publicly listed investment house utilizing a club-deal model backed by prominent entrepreneurial families to provide long-term capital to Italian champions like Interpump, Bending Spoons, and Eataly.
- target_reason: explicit

Current portfolio entries in our DB (all):
[
  {
    "name": "Amplifon",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Milan, Italy",
    "description": "Global leader in hearing solutions, listed on Borsa Italiana",
    "website": "https://www.amplifon.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Interpump Group",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Sant'Ilario d'Enza, Italy",
    "description": "Italian hydraulics and industrial equipment manufacturer",
    "website": "https://www.interpumpgroup.it",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Eataly",
    "status": "current",
    "sector": "Food & Beverage",
    "headquarters": "Monticello d'Alba, Italy",
    "description": "International marketplace and restaurant chain dedicated to high-quality Italian food and wine.",
    "website": "https://www.eataly.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Alpitour",
    "status": "current",
    "sector": "Hospitality & Tourism",
    "headquarters": "Turin, Italy",
    "description": "Italian tourism leader with an integrated model: tour operator, airline, hotel & resort management and incoming services. Under Wise Equity ownership, Alpitour has completed five acquisitions and invested heavily in technology.",
    "website": "https://www.alpitour.it/",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Bending Spoons",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Milano, Italy",
    "description": "Founded in 2013 in Copenhagen by four young entrepreneurs and headquartered in Milan, Bending Spoons is a data-driven and data-centric digital company specialized in the acquisition, development and monetization of mobile apps, mainly on Apple’s platform iOS. ",
    "website": "https://bendingspoons.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "OVS",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Mestre, Italy",
    "description": "Italian fast fashion retailer, listed on Borsa Italiana",
    "website": "https://www.ovs.it",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Hugo Boss",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Metzingen, Germany",
    "description": "German luxury fashion house",
    "website": "https://www.hugoboss.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Prysmian",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Milan, Italy",
    "description": "World leader in cables and energy/telecom systems",
    "website": "https://www.prysmian.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Roche Bobois",
    "status": "current",
    "sector": "Consumer Goods",
    "headquarters": "Paris, France",
    "description": "French luxury furniture brand",
    "website": "https://www.roche-bobois.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Engineering Ingegneria Informatica",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Rome, Italy",
    "description": "Engineering Ingegneria Informatica is a leading IT services and software company that provides digital transformation solutions to public and private organizations. It specializes in areas such as cloud computing, cybersecurity, and business process outsourcin",
    "website": null,
    "investment_date": null,
    "source_url": null,
    "data_source": null
  }
]

Likely Italy-relevant entries subset (HQ/text hints):
[
  {
    "name": "Amplifon",
    "status": "current",
    "sector": "Healthcare",
    "headquarters": "Milan, Italy",
    "description": "Global leader in hearing solutions, listed on Borsa Italiana",
    "website": "https://www.amplifon.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Interpump Group",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Sant'Ilario d'Enza, Italy",
    "description": "Italian hydraulics and industrial equipment manufacturer",
    "website": "https://www.interpumpgroup.it",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Eataly",
    "status": "current",
    "sector": "Food & Beverage",
    "headquarters": "Monticello d'Alba, Italy",
    "description": "International marketplace and restaurant chain dedicated to high-quality Italian food and wine.",
    "website": "https://www.eataly.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Alpitour",
    "status": "current",
    "sector": "Hospitality & Tourism",
    "headquarters": "Turin, Italy",
    "description": "Italian tourism leader with an integrated model: tour operator, airline, hotel & resort management and incoming services. Under Wise Equity ownership, Alpitour has completed five acquisitions and invested heavily in technology.",
    "website": "https://www.alpitour.it/",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Bending Spoons",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Milano, Italy",
    "description": "Founded in 2013 in Copenhagen by four young entrepreneurs and headquartered in Milan, Bending Spoons is a data-driven and data-centric digital company specialized in the acquisition, development and monetization of mobile apps, mainly on Apple’s platform iOS. ",
    "website": "https://bendingspoons.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "OVS",
    "status": "current",
    "sector": "Fashion & Luxury",
    "headquarters": "Mestre, Italy",
    "description": "Italian fast fashion retailer, listed on Borsa Italiana",
    "website": "https://www.ovs.it",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Prysmian",
    "status": "current",
    "sector": "Industrial Manufacturing",
    "headquarters": "Milan, Italy",
    "description": "World leader in cables and energy/telecom systems",
    "website": "https://www.prysmian.com",
    "investment_date": null,
    "source_url": null,
    "data_source": null
  },
  {
    "name": "Engineering Ingegneria Informatica",
    "status": "current",
    "sector": "Technology",
    "headquarters": "Rome, Italy",
    "description": "Engineering Ingegneria Informatica is a leading IT services and software company that provides digital transformation solutions to public and private organizations. It specializes in areas such as cloud computing, cybersecurity, and business process outsourcin",
    "website": null,
    "investment_date": null,
    "source_url": null,
    "data_source": null
  }
]

Existing names list (for duplicate filtering):
["Amplifon", "Interpump Group", "Eataly", "Alpitour", "Bending Spoons", "OVS", "Hugo Boss", "Prysmian", "Roche Bobois", "Engineering Ingegneria Informatica"]

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
