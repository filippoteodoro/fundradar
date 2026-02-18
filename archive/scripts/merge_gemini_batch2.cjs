#!/usr/bin/env node
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
  let match = entries.findIndex(e => normalize(e.name) === normTarget);
  if (match >= 0) return match;
  const compactTarget = normTarget.replace(/\s/g, '');
  match = entries.findIndex(e => normalize(e.name).replace(/\s/g, '') === compactTarget);
  if (match >= 0) return match;
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

function makeEntry(name, sector, status, description, hq, investmentDate, sourceUrl) {
  return {
    name,
    sector,
    status: status || 'current',
    confidence: 0.9,
    website: null,
    description: description || null,
    detail_page_url: null,
    headquarters: hq || null,
    investment_date: investmentDate || null,
    source_url: sourceUrl || null,
    data_source: null,
  };
}

// === ALL DATA ===

const enrichments = {
  'dea-capital-alternative-funds-sgr': [
    // Fix name: Serraplast -> Serroplast (per fund website)
    { match: 'Serraplast', nameCorrection: 'Serroplast', updates: { headquarters: 'Rutigliano, Italy', investment_date: '2023-01-01', source_url: 'https://www.deacapitalaf.com/en/taste-of-italy-2-invests-in-serroplast/' } },
  ],
  'eos-im': [
    { match: 'Donati Group', updates: { headquarters: 'Rodengo Saiano, Italy', investment_date: '2022-01-01', source_url: 'https://www.eosimgroup.com/donati-project' } },
  ],
  'sosteneo': [
    { match: 'Enel Libra Flexsys', updates: { headquarters: 'Rome, Italy', investment_date: '2024-01-01', source_url: 'https://sosteneo.com/projects/enel-libra-flexsys-elf/' } },
  ],
  'tages-capital-sgr': [
    { match: 'IPlanet', updates: { headquarters: 'Rome, Italy' } },
  ],
  'l-b-capital-sgr': [
    { match: 'NRGfarm', updates: { source_url: 'https://www.lbcapitalsgr.it/news-e-comunicati/l-b-capital-investe-in-nrgfarm/', investment_date: '2025-01-01' } },
  ],
};

const newEntries = {
  'dea-capital-alternative-funds-sgr': [
    makeEntry('Fine Food Group', 'Food & Beverage', 'current', 'Distributor of high-quality Mexican, American, and ethnic catering products.', 'Burago di Molgora, Italy', '2025-01-01', 'https://www.deacapitalaf.com/en/taste-of-italy-2-acquires-fine-food-group/'),
    makeEntry('Roscio', 'Food & Beverage', 'current', 'Specialized producer of fresh gastronomy and ready-to-eat meals.', 'Vidigulfo, Italy', '2021-01-01', 'https://www.deacapitalaf.com/en/taste-of-italy-2-invests-in-roscio/'),
    makeEntry('Cellini Caffè (EKAF)', 'Food & Beverage', 'current', 'Leading Italian coffee roaster focused on premium blends and espresso.', 'Genoa, Italy', '2021-01-01', 'https://www.deacapitalaf.com/en/taste-of-italy-2-invests-in-cellini-caffe/'),
    makeEntry('Demetra', 'Food & Beverage', 'current', 'Processor and distributor of specialty vegetables and food products for the HoReCa channel.', "Castello d'Argile, Italy", '2022-01-01', 'https://www.deacapitalaf.com/en/taste-of-italy-2-invests-in-demetra/'),
    makeEntry('International Food', 'Food & Beverage', 'current', 'Manufacturer of plant-based beverages and vegetable milk alternatives.', 'Cervia, Italy', '2022-01-01', 'https://www.deacapitalaf.com/en/taste-of-italy-2-invests-in-international-food/'),
    makeEntry('Avantea', 'Agribusiness', 'current', 'World leader in animal biotechnology and advanced reproductive technologies for livestock.', 'Cremona, Italy', '2021-01-01', 'https://www.deacapitalaf.com/en/dea-agro-invests-in-avantea/'),
    makeEntry('Pieralisi', 'Industrial Manufacturing', 'current', 'Global leader in the production of centrifugal machines for olive oil extraction.', 'Jesi, Italy', '2020-01-01', 'https://www.deacapitalaf.com/en/idea-ccr-ii-invests-in-pieralisi/'),
  ],
  'eos-im': [
    makeEntry('Poplast', 'Industrial Manufacturing', 'current', 'Specialist in flexible packaging solutions for the food and industrial sectors.', 'Castel San Giovanni, Italy', '2019-01-01', 'https://www.eosimgroup.com/poplast-project'),
    makeEntry('Neronobile', 'Food & Beverage', 'current', 'Producer of coffee capsules and compatible pods for Italian and international markets.', 'Sarcedo, Italy', '2021-01-01', 'https://www.eosimgroup.com/nero-nobile-project'),
    makeEntry('Atex Group', 'Industrial Manufacturing', 'current', 'Global producer of non-woven fabrics for medical, hygiene, and industrial use.', 'Settimo Milanese, Italy', '2021-01-01', 'https://www.eosimgroup.com/atex-project'),
    makeEntry('EF Group', 'Media / Events & Exhibitions', 'exited', 'General contractor for the design and construction of stands and corporate environments.', 'Bologna, Italy', '2018-01-01', 'https://www.eosimgroup.com/ef-group-project'),
  ],
  'sosteneo': [
    makeEntry('San Nicola Manfredi Wind Farm', 'Renewable Energy', 'current', 'Onshore wind infrastructure project in Southern Italy.', 'San Nicola Manfredi, Italy', '2023-01-01', 'https://sosteneo.com/projects/san-nicola-manfredi/'),
    makeEntry('Ramacca Solar Farm', 'Renewable Energy', 'current', 'Large-scale photovoltaic project in Sicily.', 'Ramacca, Italy', '2023-01-01', 'https://sosteneo.com/projects/ramacca-solar-farm/'),
  ],
  'tages-capital-sgr': [
    makeEntry('Delos Service', 'Energy Services', 'current', 'Asset management and operation/maintenance company for Tages renewable plant portfolio.', 'Milan, Italy', '2019-01-01', 'https://www.tagescapitalsgr.com/en/tages-helios-net-zero-fund/'),
  ],
  'kairos-partners-sgr': [
    makeEntry('Underscore District', 'Technology', 'current', 'Accelerator for independent luxury and fashion brands focused on digital transformation.', 'Milan, Italy', '2024-01-01', 'https://bebeez.it/venture-capital/kairos-ventures-esg-one-investe-in-underscore-district/'),
    makeEntry('Materia Medica Processing', 'Healthcare', 'current', 'Startup focused on phytochemistry and pharmaceutical extraction from medical cannabis.', 'Montecarlo, Italy', '2022-01-01', 'https://dirittoeaffari.it/chiomenti-e-legalitax-nellinvestimento-in-materia-medica-processing/'),
  ],
  'ream-sgr': [
    makeEntry('RSA Lancia & RSA Caraglio', 'Healthcare', 'current', 'Two integrated nursing homes (RSA) providing 400 total beds for elderly care.', 'Turin, Italy', '2022-01-01', 'https://www.reamsgr.it/comunicazione/comunicati-e-notizie/ream-sgr-procede-nell-acquisizione-di-residenze-sanitarie-assistenziali-per-conto-del-fondo-geras.html'),
    makeEntry('Adriano Community Center', 'Healthcare', 'current', 'Multi-use healthcare and community center acquired via the Geras 2 Fund.', 'Milan, Italy', '2024-01-01', 'https://www.reamsgr.it/comunicazione/comunicati-e-notizie/ream-sgr-per-conto-del-fondo-geras-2-acquista-da-proges-l-adriano-community-center-a-milano.html'),
    makeEntry('CeMeDi', 'Healthcare', 'current', 'Historic medical clinic asset acquired from FCA Partecipazioni in Turin.', 'Turin, Italy', '2025-01-01', 'https://www.auraree.com/italy/real-estate-news/ream-sgr-completed-a-new-acquisition-in-the-healthcare-sector-in-turin/'),
  ],
};

// === MERGE ===
const data = JSON.parse(fs.readFileSync(PORTFOLIO_PATH, 'utf8'));
let enrichCount = 0;
let addCount = 0;

// Enrichments
for (const [slug, updates] of Object.entries(enrichments)) {
  const entries = data.fund_portfolios[slug];
  if (!entries) { console.log('WARN: No portfolio array for ' + slug); continue; }
  for (const { match: matchName, updates: fields, nameCorrection } of updates) {
    const idx = findMatch(entries, matchName);
    if (idx < 0) { console.log('WARN: No match for "' + matchName + '" in ' + slug); continue; }
    let updated = false;
    if (nameCorrection && entries[idx].name !== nameCorrection) {
      console.log('  NAME FIX: ' + entries[idx].name + ' -> ' + nameCorrection);
      entries[idx].name = nameCorrection;
      updated = true;
    }
    for (const [key, value] of Object.entries(fields)) {
      if (entries[idx][key] === null || entries[idx][key] === undefined) {
        entries[idx][key] = value;
        updated = true;
      }
    }
    if (updated) { enrichCount++; console.log('ENRICHED: ' + slug + ' / ' + entries[idx].name); }
  }
}

// New entries
for (const [slug, entries] of Object.entries(newEntries)) {
  if (!data.fund_portfolios[slug]) data.fund_portfolios[slug] = [];
  const existing = data.fund_portfolios[slug];
  for (const entry of entries) {
    const idx = findMatch(existing, entry.name);
    if (idx >= 0) {
      // Still enrich missing fields on the existing entry
      let updated = false;
      for (const key of ['headquarters', 'description', 'investment_date', 'source_url', 'sector']) {
        if ((existing[idx][key] === null || existing[idx][key] === undefined) && entry[key]) {
          existing[idx][key] = entry[key];
          updated = true;
        }
      }
      if (updated) { enrichCount++; console.log('ENRICHED (via new): ' + slug + ' / ' + existing[idx].name); }
      else { console.log('SKIP (exists): ' + slug + ' / ' + entry.name + ' matched ' + existing[idx].name); }
      continue;
    }
    existing.push(entry);
    addCount++;
    console.log('ADDED: ' + slug + ' / ' + entry.name);
  }
}

// Write
const tmpPath = PORTFOLIO_PATH + '.tmp';
fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2) + '\n');
fs.renameSync(tmpPath, PORTFOLIO_PATH);
console.log('\nDone: ' + enrichCount + ' enriched, ' + addCount + ' added');
