#!/usr/bin/env node
/**
 * One-time script to merge manually researched portfolio data into portfolio_items.json.
 * - Enriches existing entries with missing fields (headquarters, description, investment_date, source_url)
 * - Adds new entries that don't exist yet
 * - Never overwrites existing non-null values
 */
const fs = require('fs');
const path = require('path');

const PORTFOLIO_PATH = path.join(__dirname, '..', 'data', 'derived', 'portfolio_items.json');

function normalize(name) {
  return name.toLowerCase()
    .replace(/\s*\(.*?\)\s*/g, ' ')
    .replace(/\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?)\b/gi, '')
    .replace(/\bgroup\b/gi, '')
    .replace(/\btechnologies\b/gi, '')
    .replace(/[^a-z0-9]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function findMatch(entries, targetName) {
  const normTarget = normalize(targetName);
  // Exact normalized match
  let match = entries.findIndex(e => normalize(e.name) === normTarget);
  if (match >= 0) return match;
  // Compact match (no spaces)
  const compactTarget = normTarget.replace(/\s/g, '');
  match = entries.findIndex(e => normalize(e.name).replace(/\s/g, '') === compactTarget);
  if (match >= 0) return match;
  // Substring match (both >= 5 chars)
  if (compactTarget.length >= 5) {
    match = entries.findIndex(e => {
      const compactE = normalize(e.name).replace(/\s/g, '');
      if (compactE.length < 5) return false;
      const shorter = compactTarget.length <= compactE.length ? compactTarget : compactE;
      const longer = compactTarget.length <= compactE.length ? compactE : compactTarget;
      return longer.includes(shorter);
    });
    if (match >= 0) return match;
  }
  return -1;
}

// === DATA TO MERGE ===

const enrichments = {
  'amber-capital': [
    { match: 'Italian Exhibition Group', updates: { investment_date: '2019-01-01', source_url: 'https://it.fashionnetwork.com/news/Italian-exhibition-group-amber-capital-italia-sgr-supera-il-10-di-ieg,1640801.html' } },
  ],
  'arca-space-capital': [
    { match: 'RINA', updates: { investment_date: '2023-01-01' } },
    { match: 'Unifarco', updates: { investment_date: '2025-01-01', source_url: 'https://www.spacecapital.it/news/investimento-in-unifarco-spa/' } },
  ],
  'partners-group': [
    { match: 'OnPlace', updates: { source_url: 'https://www.partnersgroup.com/en/news-and-views/press-releases/corporate-news/detail?news_id=1776b652-ec9d-4196-b8f7-5ac5676f6fed' } },
    { match: 'Telepass', updates: { headquarters: 'Rome, Italy' } },
    { match: 'Eolo', updates: { headquarters: 'Busto Arsizio, Italy' } },
  ],
  'ares-management': [
    { match: 'Plenitude', updates: { source_url: 'https://www.eni.com/en-IT/media/press-release/2025/11/eni-completed-sale-20-take-plenitude-ares-management-alternative-credit-funds.html', headquarters: 'San Donato Milanese, Italy' } },
  ],
  'carlyle': [
    { match: 'Forgital', updates: { source_url: 'https://www.carlyle.com/our-business/portfolio-of-investments/forgital', headquarters: 'Velo d\'Astico, Italy' } },
    { match: 'Design Holding', updates: { source_url: 'https://www.carlyle.com/our-business/portfolio-of-investments/flos-bb-italia' } },
    { match: 'Golden Goose', updates: { source_url: 'https://www.carlyle.com/our-business/portfolio-of-investments/golden-goose-deluxe-brand', headquarters: 'Milan, Italy' } },
  ],
  'apheon': [
    { match: 'Golmar', updates: { source_url: 'https://www.pehub.com/apheon-takes-majority-control-of-golmar-italia/', headquarters: 'Milan, Italy' } },
    { match: 'Salpa', updates: { headquarters: 'Perugia, Italy' } },
  ],
  'sagard': [
    { match: 'FOS', updates: { } },
  ],
  'alternative-capital-partners-sgr': [
    { match: 'Energethica Favria', updates: { headquarters: 'Favria, Italy' } },
  ],
};

const newEntries = {
  'partners-group': [
    {
      name: 'AMMEGA / Megadyne',
      sector: 'Industrial Manufacturing',
      status: 'current',
      confidence: 0.9,
      website: null,
      description: 'Power transmission belts and related components group (acquired Megadyne).',
      detail_page_url: null,
      headquarters: 'Mathi, Italy',
      investment_date: null,
      source_url: 'https://www.partnersgroup.com/en/news-and-views/press-releases/investment-news/detail?news_id=e51b6248-6d35-4e1e-970e-0b3e73a3efbf',
      data_source: null,
    },
  ],
  'alternative-capital-partners-sgr': [
    {
      name: 'CTIP Blu',
      sector: 'Renewable Energy',
      status: 'current',
      confidence: 0.9,
      website: null,
      description: 'Biomethane plant project (FORSU-fed) in Abruzzo.',
      detail_page_url: null,
      headquarters: 'Mosciano Sant\'Angelo, Italy',
      investment_date: null,
      source_url: 'https://alternativecapital.partners/2023/02/10/acp-sgr-co-arranger-del-finanziamento-di-19-milioni-di-euro-sottoscritto-da-ctip-blu-con-banco-bpm-e-bper/',
      data_source: null,
    },
    {
      name: 'Bia Power Italia',
      sector: 'Renewable Energy',
      status: 'current',
      confidence: 0.9,
      website: null,
      description: 'Development capital to expand Italian BESS pipeline (JV with EREN).',
      detail_page_url: null,
      headquarters: null,
      investment_date: null,
      source_url: 'https://alternativecapital.partners/2025/12/09/acp-sgr-tramite-il-fondo-ssf-entra-in-bia-power-per-supportare-la-joint-venture-bess-da-750-mw-con-eren/',
      data_source: null,
    },
    {
      name: 'Cogefeed Impact',
      sector: 'Renewable Energy',
      status: 'current',
      confidence: 0.9,
      website: null,
      description: 'JV to build small/medium greenfield PV platform across central Italy.',
      detail_page_url: null,
      headquarters: null,
      investment_date: null,
      source_url: null,
      data_source: null,
    },
    {
      name: 'Solterra / Sb Impact',
      sector: 'Renewable Energy',
      status: 'current',
      confidence: 0.9,
      website: null,
      description: 'PV/agrivoltaic pipeline including projects in Rovigo, Piacenza d\'Adige, and Sermide.',
      detail_page_url: null,
      headquarters: 'Rovigo, Italy',
      investment_date: null,
      source_url: 'https://alternativecapital.partners/2024/05/29/acp-sgr-firmato-il-closing-con-solterra-per-sviluppare-fino-a-100mwp-di-fotovoltaico-nel-centro-nord-italia/',
      data_source: null,
    },
    {
      name: 'Ilios Impact',
      sector: 'Renewable Energy',
      status: 'current',
      confidence: 0.9,
      website: null,
      description: 'Agrivoltaic development projects in the Foggia area.',
      detail_page_url: null,
      headquarters: 'Foggia, Italy',
      investment_date: null,
      source_url: null,
      data_source: null,
    },
  ],
  'sagard': [
    {
      name: 'GV3-Venpa',
      sector: 'Industrial Services',
      status: 'current',
      confidence: 0.9,
      website: null,
      description: 'Rental of lifting/construction/earthmoving equipment.',
      detail_page_url: null,
      headquarters: 'Dolo, Italy',
      investment_date: null,
      source_url: 'https://www.internationalrentalnews.com/news/venpa-sells-majority-share-to-private-equity/8039635.article',
      data_source: null,
    },
  ],
};

// === MERGE LOGIC ===

const data = JSON.parse(fs.readFileSync(PORTFOLIO_PATH, 'utf8'));
let enrichCount = 0;
let addCount = 0;

// 1. Enrich existing entries
for (const [slug, updates] of Object.entries(enrichments)) {
  const entries = data.fund_portfolios[slug];
  if (!entries) {
    console.log(`WARN: No portfolio array for ${slug}`);
    continue;
  }
  for (const { match: matchName, updates: fields } of updates) {
    const idx = findMatch(entries, matchName);
    if (idx < 0) {
      console.log(`WARN: No match for "${matchName}" in ${slug}`);
      continue;
    }
    let updated = false;
    for (const [key, value] of Object.entries(fields)) {
      if (entries[idx][key] === null || entries[idx][key] === undefined) {
        entries[idx][key] = value;
        updated = true;
      }
    }
    if (updated) {
      enrichCount++;
      console.log(`ENRICHED: ${slug} / ${entries[idx].name}`);
    }
  }
}

// 2. Add new entries
for (const [slug, entries] of Object.entries(newEntries)) {
  if (!data.fund_portfolios[slug]) {
    data.fund_portfolios[slug] = [];
  }
  const existing = data.fund_portfolios[slug];
  for (const entry of entries) {
    const idx = findMatch(existing, entry.name);
    if (idx >= 0) {
      console.log(`SKIP (exists): ${slug} / ${entry.name} matched ${existing[idx].name}`);
      continue;
    }
    existing.push(entry);
    addCount++;
    console.log(`ADDED: ${slug} / ${entry.name}`);
  }
}

// 3. Write
const tmpPath = PORTFOLIO_PATH + '.tmp';
fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2) + '\n');
fs.renameSync(tmpPath, PORTFOLIO_PATH);

console.log(`\nDone: ${enrichCount} enriched, ${addCount} added`);
