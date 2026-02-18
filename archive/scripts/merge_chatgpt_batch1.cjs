#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const PORTFOLIO_PATH = path.join(__dirname, '..', 'data', 'derived', 'portfolio_items.json');

function normalize(name) {
  return name.toLowerCase()
    .replace(/\s*\(.*?\)\s*/g, ' ')
    .replace(/\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?)\b/gi, '')
    .replace(/\bgroup\b/gi, '')
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

function mk(name, sector, status, desc, hq, date, src) {
  return {
    name, sector, status: status || 'current', confidence: 0.9,
    website: null, description: desc || null, detail_page_url: null,
    headquarters: hq || null, investment_date: date || null,
    source_url: src || null, data_source: null,
  };
}

const data = JSON.parse(fs.readFileSync(PORTFOLIO_PATH, 'utf8'));
let addCount = 0, enrichCount = 0, removeCount = 0;

// === 1. REMOVE GARBAGE ===
const garbageRemovals = {
  'entangled-capital-sgr': ['icon', 'arrow'],
  'wrm-group': ['Oops!'],
};
for (const [slug, names] of Object.entries(garbageRemovals)) {
  const entries = data.fund_portfolios[slug];
  if (!entries) continue;
  for (const name of names) {
    const idx = entries.findIndex(e => e.name === name);
    if (idx >= 0) {
      entries.splice(idx, 1);
      removeCount++;
      console.log('REMOVED garbage: ' + slug + ' / ' + name);
    }
  }
}

// === 2. ENRICHMENTS ===
const enrichments = {
  'dbag-italia': [
    { match: 'Great Lengths', updates: { headquarters: 'Nepi, Italy', investment_date: '2024-01-01', source_url: 'https://www.dbagitalia.com/attuali-investimenti/great-lengths/' } },
  ],
  'kyip-capital-sgr': [
    { match: 'Confident', updates: { headquarters: 'Gallarate, Italy', investment_date: '2025-01-01', source_url: 'https://kyipcapital.com/en/investments/confident/' } },
  ],
  'rancilio-cube-sicaf': [
    { match: 'Casavo', updates: { headquarters: 'Milan, Italy' } },
    { match: 'Treedom', updates: { headquarters: 'Florence, Italy' } },
  ],
};
for (const [slug, updates] of Object.entries(enrichments)) {
  const entries = data.fund_portfolios[slug];
  if (!entries) { console.log('WARN: No array for ' + slug); continue; }
  for (const { match: matchName, updates: fields } of updates) {
    const idx = findMatch(entries, matchName);
    if (idx < 0) { console.log('WARN: No match for "' + matchName + '" in ' + slug); continue; }
    let updated = false;
    for (const [key, value] of Object.entries(fields)) {
      if (entries[idx][key] === null || entries[idx][key] === undefined) {
        entries[idx][key] = value;
        updated = true;
      }
    }
    if (updated) { enrichCount++; console.log('ENRICHED: ' + slug + ' / ' + entries[idx].name); }
  }
}

// === 3. NEW ENTRIES ===
const newEntries = {
  'como-venture': [
    mk('D-Orbit', 'Aerospace', 'current', 'Italian space logistics company providing in-orbit transportation and related services.', 'Fino Mornasco, Italy', null, 'https://www.comoventure.it/holdings.htm'),
    mk('Leaf Space', 'Telecommunications', 'current', 'Provider of ground-segment services and ground-station network solutions for satellite communications.', 'Lomazzo, Italy', null, 'https://www.comoventure.it/holdings.htm'),
    mk('Directa Plus', 'Advanced Materials', 'current', 'Producer of graphene-based products for industrial and consumer applications.', 'Lomazzo, Italy', null, 'https://www.comoventure.it/holdings.htm'),
    mk('DialyBrid', 'Healthcare', 'current', 'Healthcare digital/telemedicine-focused company.', null, null, 'https://www.comoventure.it/holdings.htm'),
  ],
  'siryo': [
    mk('EggPlant', 'Food & Beverage', 'current', 'Food innovation company focused on alternative ingredients.', 'Bari, Italy', null, 'https://www.siryo.it/en/portfolio/eggplant/'),
    mk('Celery Ingredients', 'Healthcare', 'current', 'Develops natural functional ingredients from plant sources for food and health applications.', 'Polignano a Mare, Italy', '2022-01-01', 'https://bebeez.it/venture-capital/celery-ingredients-raccoglie-25-milioni-di-euro-anche-da-siryo-holding-s1-per-scalare-la-produzione-e-accordi-commerciali/'),
    mk('Postbiotica', 'Healthcare', 'current', 'Biotech startup focused on postbiotics and microbiome-based applications.', 'Milan, Italy', '2021-01-01', 'https://www.legalcommunity.it/postbiotica-aumento-di-capitale/'),
  ],
  'dbag-italia': [
    mk('MTWH', 'Industrial Manufacturing', 'current', 'Manufacturer of high-quality metal applications and components used in luxury goods and industrial uses.', null, '2022-01-01', 'https://www.dbagitalia.com/dbag-in-italia-partita-con-il-piede-giusto/'),
  ],
  'kyip-capital-sgr': [
    mk('Datlas Group', 'Technology', 'current', 'Italian business process-as-a-service platform combining proprietary digital tools with operational delivery.', 'Milan, Italy', '2021-01-01', 'https://kyipcapital.com/en/investments/datlas/'),
    mk('Plena Education', 'Education', 'current', 'Holding platform aggregating Italian fine-arts schools and programs.', 'Milan, Italy', '2022-01-01', 'https://kyipcapital.com/en/portfolio-company-plena-education-secures-e10-million-funding-to-accelerate-its-growth-plan/'),
    mk('Volta Institute', 'Education', 'current', 'Provider of vocational education and professional training programs.', 'Bari, Italy', '2024-01-01', 'https://kyipcapital.com/en/investments/istituto-volta/'),
    mk('Errevi System', 'Technology', 'current', 'ICT services company supporting digital transformation (cloud, cybersecurity, business applications).', 'Reggio Emilia, Italy', '2024-01-01', 'https://kyipcapital.com/en/investments/errevi/'),
    mk('ETJCA', 'Business Services', 'current', 'Italian human-capital services platform offering integrated staffing and HR solutions.', null, '2025-01-01', 'https://kyipcapital.com/en/investments/etjca/'),
  ],
  'avm': [
    mk('Roboze', 'Industrial Manufacturing', 'current', 'Developer of high-performance 3D printers and advanced polymer materials for industrial applications.', null, null, 'https://adhoccommunication.it/wp-content/uploads/2024/06/CS_AVM-Rialto-Ventures_4-giugno-2024.pdf'),
    mk('Aidem', 'Industrial Manufacturing', 'current', 'Industrial technology/automation company.', null, null, 'https://adhoccommunication.it/wp-content/uploads/2024/06/CS_AVM-Rialto-Ventures_4-giugno-2024.pdf'),
    mk('Platformatic', 'Technology', 'current', 'Software platform company providing developer tools.', null, null, 'https://adhoccommunication.it/wp-content/uploads/2024/06/CS_AVM-Rialto-Ventures_4-giugno-2024.pdf'),
    mk('K-Sport', 'Technology', 'current', 'Sports performance technology and wearables company.', null, null, 'https://adhoccommunication.it/wp-content/uploads/2024/06/CS_AVM-Rialto-Ventures_4-giugno-2024.pdf'),
    mk('Keyless', 'Technology', 'current', 'Digital identity and security company.', null, null, 'https://adhoccommunication.it/wp-content/uploads/2024/06/CS_AVM-Rialto-Ventures_4-giugno-2024.pdf'),
    mk('Medicilio', 'Healthcare', 'current', 'Healthcare services platform for home medical care.', null, null, 'https://adhoccommunication.it/wp-content/uploads/2024/06/CS_AVM-Rialto-Ventures_4-giugno-2024.pdf'),
  ],
  'entangled-capital-sgr': [
    mk('SIPA International', 'Food & Beverage', 'current', 'Producer of couscous and grain-based products marketed under the Martino brand.', 'Campochiaro, Italy', null, 'https://entangledcapital.com/en/portfolio/'),
    mk('Tecnomaster', 'Industrial Manufacturing', 'current', 'Electronics/PCB manufacturing group.', 'Pavia di Udine, Italy', null, 'https://entangledcapital.com/en/portfolio/'),
    mk('FBL Food Machinery', 'Industrial Manufacturing', 'current', 'Manufacturer of machinery and lines for the food industry.', 'Noceto, Italy', null, 'https://entangledcapital.com/en/portfolio/'),
    mk('Airpower Group', 'Industrial Manufacturing', 'current', 'Supplier of glazing and finishing lines for the ceramic industry.', 'Sassuolo, Italy', null, 'https://entangledcapital.com/en/portfolio/'),
    mk('Turatti & Tecnoceam', 'Industrial Manufacturing', 'current', 'Designs and manufactures machinery/lines for food processing.', 'Cavarzere, Italy', null, 'https://entangledcapital.com/en/portfolio/'),
    mk('Pasquini & Bini', 'Industrial Manufacturing', 'current', 'Industrial automation and handling equipment company.', 'Altopascio, Italy', null, 'https://entangledcapital.com/en/portfolio/'),
    mk('Alphial', 'Industrial Manufacturing', 'exited', 'Producer of primary pharmaceutical glass packaging (ampoules and vials).', 'Treviglio, Italy', '2022-01-01', 'https://entangledcapital.com/en/portfolio/alphial/'),
  ],
  'wrm-group': [
    mk('Gruppo Kipre', 'Food & Beverage', 'current', 'Italian cured-meat group including DOP prosciutto activities, acquired via turnaround process.', null, '2020-01-01', 'https://wrmgroup.net/wp-content/uploads/2022/02/WRM-ACQUISITION-OF-KIPRE-GROUP_it.pdf'),
  ],
};

for (const [slug, entries] of Object.entries(newEntries)) {
  if (!data.fund_portfolios[slug]) data.fund_portfolios[slug] = [];
  const existing = data.fund_portfolios[slug];
  for (const entry of entries) {
    const idx = findMatch(existing, entry.name);
    if (idx >= 0) {
      let updated = false;
      for (const key of ['headquarters', 'description', 'investment_date', 'source_url', 'sector']) {
        if ((existing[idx][key] === null || existing[idx][key] === undefined) && entry[key]) {
          existing[idx][key] = entry[key];
          updated = true;
        }
      }
      if (updated) { enrichCount++; console.log('ENRICHED (via new): ' + slug + ' / ' + existing[idx].name); }
      else { console.log('SKIP: ' + slug + ' / ' + entry.name + ' matched ' + existing[idx].name); }
      continue;
    }
    existing.push(entry);
    addCount++;
    console.log('ADDED: ' + slug + ' / ' + entry.name);
  }
}

// === 4. PORTFOLIO NOTES ===
const notes = {
  'canova-sgr': 'Canova SGR does not publish investee company names on its public website.',
  'faro-value': 'FARO Value operates as an advisory platform within the FARO Alternative Investments ecosystem rather than holding direct equity stakes.',
  'hat-sicaf': 'HAT Sicaf does not publicly map current holdings to this specific investment vehicle.',
  'private-equity-partners': 'Private Equity Partners does not publish a public portfolio list identifying current equity holdings.',
  'star-tech-ventures': 'No public portfolio data is currently available for Star Tech Ventures.',
  'sagitta-sgr': 'Sagitta SGR does not publish a public list of current equity stakes in portfolio companies.',
  'sinloc-investimenti-sgr': 'Sinloc Investimenti SGR invests via SPVs in infrastructure and energy transition projects. Individual project names are not publicly disclosed.',
  '8a-investimenti-sgr': 'No public portfolio list is available identifying current private-company equity stakes for 8a+ Investimenti SGR.',
  'polis-sgr-groupe-lbo-france': 'No verifiable portfolio page or deal announcements attributable to Polis SGR were found in public sources.',
  'prana-ventures': 'Prana Ventures does not publish a public portfolio list on its website.',
  'finint-investments-sgr': 'No public portfolio data listing specific current infrastructure assets was found for Finint Investments SGR.',
};

// Check which slugs exist in db before adding notes
if (!data.fund_portfolio_notes) data.fund_portfolio_notes = {};
let noteCount = 0;
for (const [slug, note] of Object.entries(notes)) {
  if (!data.fund_portfolio_notes[slug]) {
    data.fund_portfolio_notes[slug] = note;
    noteCount++;
    console.log('NOTE: ' + slug);
  }
}

// Write
const tmp = PORTFOLIO_PATH + '.tmp';
fs.writeFileSync(tmp, JSON.stringify(data, null, 2) + '\n');
fs.renameSync(tmp, PORTFOLIO_PATH);
console.log('\nDone: ' + removeCount + ' removed, ' + enrichCount + ' enriched, ' + addCount + ' added, ' + noteCount + ' notes');
