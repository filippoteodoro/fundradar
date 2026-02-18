/**
 * Enrich portfolio companies with sector classifications.
 *
 * One-time script. Only overwrites null sectors — existing sectors preserved.
 *
 * Usage: cd scripts && npx tsx enrich-sectors.ts
 */

import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';

const PROJECT_ROOT = join(process.cwd(), '..');
const PORTFOLIO_PATH = join(PROJECT_ROOT, 'data', 'derived', 'portfolio_items.json');

// ─── Sector assignments by fund ─────────────────────────────────────

// Map: lowercase company name → sector
type SectorMap = Record<string, string>;

const SECTOR_MAPS: Record<string, SectorMap> = {
  '21-invest': {
    'dl software': 'Technology',
    'forno d asolo': 'Food & Beverage',
    'forno dasolo': 'Food & Beverage',
    'apaczka': 'Technology',
    'parkingo': 'Business Services',
    'else solutions': 'Healthcare',
    'prosol': 'Healthcare',
    'donora': 'Technology',
    'rocamed': 'Healthcare',
    'thenicekitchen': 'Industrial',
    'productlifegroup': 'Healthcare',
    'productlife group': 'Healthcare',
    'omega pharma': 'Healthcare',
    'conex': 'Technology',
    'agorastore': 'Technology',
    'trime': 'Industrial',
    'energreen': 'Industrial',
    'in out': 'Industrial',
    'edukea group': 'Business Services',
    'tvhconsulting': 'Technology',
    'woonoz': 'Technology',
    'witors': 'Food & Beverage',
    'aussafer': 'Industrial',
    'orisha': 'Technology',
    'landanger': 'Healthcare',
    'lvoverseas': 'Business Services',
    'fma assurances': 'Financial Services',
    'zonin': 'Food & Beverage',
    'carton pack': 'Industrial',
    'gianni chiarini': 'Consumer',
    'philippe model': 'Consumer',
    'impact': 'Business Services',
    'sifi': 'Healthcare',
    'synerlab': 'Healthcare',
    'viabizzuno': 'Industrial',
    'maxicoffee': 'Food & Beverage',
    'poligof': 'Industrial',
    'nadella': 'Industrial',
    'farnese 2': 'Food & Beverage',
    'assicom': 'Financial Services',
    'pittarosso': 'Consumer',
    'skill you': 'Business Services',
    'coyote': 'Technology',
    'rgi': 'Technology',
    'gpp': 'Industrial',
    'valbart': 'Industrial',
    'interflora': 'Consumer',
    'the space cinema 2': 'Media & Telecom',
  },
  'alto-partners-sgr': {
    'gallo': 'Consumer',
    'eurosirel': 'Healthcare',
    'fradiavolo': 'Food & Beverage',
    'ef group': 'Business Services',
    'dierre group': 'Industrial',
    'lario plast': 'Industrial',
    'cei ii': 'Industrial',
    'cei': 'Industrial',
    'dmx pharma': 'Healthcare',
    'diatech': 'Healthcare',
    'olimpia splendid': 'Industrial',
    'ofi': 'Healthcare',
    'bia': 'Food & Beverage',
    'millefili': 'Consumer',
    'tricobiotos': 'Consumer',
    'dolciaria val d\'enza': 'Food & Beverage',
    'dolciaria val d\u2019enza': 'Food & Beverage',
    'la suissa': 'Food & Beverage',
    'virosac': 'Industrial',
    'artebianca': 'Food & Beverage',
    'pastificio di chiavenna': 'Food & Beverage',
    'semenzato': 'Food & Beverage',
    'ipe visionnaire': 'Consumer',
    'harbor': 'Consumer',
    'legami': 'Consumer',
    'monviso': 'Food & Beverage',
    'gruppo arcte': 'Consumer',
    'rancilio group': 'Industrial',
    'caminetti montegrappa': 'Industrial',
    'drogheria e alimentari': 'Food & Beverage',
    'idm': 'Business Services',
    'diquigiovanni': 'Industrial',
    'trevisanalat': 'Food & Beverage',
    'rtp viareggio ponsi': 'Industrial',
  },

  'vertis-sgr': {
    'titan4': 'Technology',
    'live story': 'Technology',
    'scuter': 'Technology',
    'tuidi': 'Technology',
    'xbooks': 'Technology',
    'timeflow': 'Technology',
    'focoos ai': 'Technology',
    'wellhub': 'Business Services',
    'starting finance': 'Financial Services',
    'ncore hr': 'Technology',
    'coverzen': 'Financial Services',
    'deliveristo': 'Food & Beverage',
    'aindo': 'Technology',
    'smallpixels': 'Technology',
    'quicklypro': 'Healthcare',
    'skinlabo': 'Consumer',
    'fitprime': 'Business Services',
    'fitprime | invested by vertis sgr': 'Business Services',
    'zerynth': 'Technology',
    'hexadrive engineering': 'Industrial',
    'radical storage formerly bagbnb': 'Business Services',
    'radical storage formerly bagbnb | vertis sgr subsidiary': 'Business Services',
    'entando': 'Technology',
    'sibylla biotech': 'Healthcare',
    'often medical': 'Healthcare',
    'intendime': 'Healthcare',
    'buzzoole': 'Technology',
    'heaxel': 'Technology',
    'vr media': 'Media & Telecom',
    'milkman': 'Technology',
    'credimi': 'Financial Services',
    'cyber dyne': 'Technology',
    'cyber \u200b\u200bdyne | vertis sgr spa': 'Technology',
    'sclak': 'Technology',
    'toothpic': 'Technology',
    'toothpic | vertis sgr spa': 'Technology',
    'selematic': 'Industrial',
    'preziosi food': 'Food & Beverage',
    'giplast group': 'Industrial',
    'wib': 'Technology',
    'plugg': 'Technology',
    'chef dovunque': 'Food & Beverage',
    'titano': 'Industrial',
    'jusp': 'Financial Services',
    'arav fashion': 'Consumer',
    'fluidotecnica sanseverino': 'Industrial',
    'cosigen': 'Industrial',
    'linkpass': 'Technology',
    'paperlit': 'Media & Telecom',
    'paperlit | vertis sgr spa': 'Media & Telecom',
    'vivocha': 'Technology',
    'karalit': 'Technology',
    'derev': 'Technology',
    'wisco': 'Industrial',
    'blomming': 'Technology',
    'promoqui': 'Technology',
    'autoxy': 'Technology',
    'optimares': 'Industrial',
    'optimares | vertis sgr spa': 'Industrial',
    'biouniversa': 'Healthcare',
    'money 360': 'Financial Services',
    'glomeria therapeutics': 'Healthcare',
    'personal factory': 'Industrial',
    'mosaicoon': 'Media & Telecom',
  },

  // ─── Phase 1: C-grade funds near B threshold ──────────────────────

  'equinox-aifm': {
    'modulblok': 'Industrial',
    'migal group': 'Industrial',
    'salpa & cherubini': 'Industrial',
    'pizzium': 'Food & Beverage',
    'pedemonte group': 'Industrial',
    'clas': 'Consumer',
    'mvc group': 'Industrial',
    'quid informatica': 'Technology',
    'adler': 'Industrial',
    'liva nova': 'Healthcare',
    'alitalia': 'Infrastructure',
    'bio energie': 'Energy',
    'hopa': 'Financial Services',
    'airfour': 'Industrial',
    'esaote': 'Healthcare',
    'citterio': 'Food & Beverage',
    'fisia italimpianti': 'Infrastructure',
    "church's": 'Consumer',
    'intercos': 'Consumer',
    'manuli film': 'Industrial',
    'moby': 'Infrastructure',
  },
  'avanzi-etica-sicaf-euveca': {
    'amalia care': 'Healthcare',
    'id eight': 'Consumer',
    'personae': 'Business Services',
    'alluneed': 'Technology',
    'wonderful italy srl': 'Consumer',
    'ecozema srl societa benefit': 'Industrial',
    'rifo srl societa benefit': 'Consumer',
    'test1 srl societa benefit': 'Technology',
    'genome up srl societa benefit': 'Healthcare',
    'jojolly srl societa benefit': 'Business Services',
    'rice house srl societa benefit': 'Industrial',
    'euleria societa benefit srl': 'Healthcare',
    'areamedical24 societa benefit srl': 'Healthcare',
    'homa societa cooperativa': 'Real Estate',
    'casa dello studente societa benefit srl': 'Real Estate',
    'healthy ageing research group societa benefit srl harg': 'Healthcare',
    'ecornaturasi': 'Consumer',
  },
  'renaissance-partners': {
    'u-power': 'Consumer',
    'bending spoons': 'Technology',
    'neopharmed gentili': 'Healthcare',
    'inetum': 'Technology',
    'arbo': 'Industrial',
    'sicit': 'Industrial',
    'over it': 'Technology',
    'engineering': 'Technology',
    'rino mastrotto': 'Industrial',
    'hydro holding': 'Industrial',
  },
  'three-hills': {
    'act': 'Business Services',
    'alliance pharma': 'Healthcare',
    'aquafil': 'Industrial',
    'borealis': 'Industrial',
    'building energy': 'Energy',
    'byron': 'Food & Beverage',
    'caretech': 'Healthcare',
    'castellet hospitality': 'Consumer',
    'dedalus': 'Healthcare',
    'digital360': 'Technology',
  },
  'quadrivio-group': {
    'rebeya': 'Consumer',
    'pt torino': 'Consumer',
    'xtrawine': 'Food & Beverage',
    'dondup': 'Consumer',
    'gcds': 'Consumer',
    'rosantica': 'Consumer',
    'rougj': 'Healthcare',
    'prosit': 'Food & Beverage',
    '120% lino': 'Consumer',
    'twinset': 'Consumer',
    'sessun': 'Consumer',
    'sess\u00f9n': 'Consumer',
    'filippo de laurentiis': 'Consumer',
    'autry': 'Consumer',
    'creactives': 'Technology',
    'dot.net': 'Technology',
    'aton': 'Technology',
    'mauden': 'Technology',
    'prestige group': 'Consumer',
    'medisin': 'Healthcare',
    'nuova sabatini': 'Industrial',
    'gpi group': 'Healthcare',
    'la villa': 'Healthcare',
    'villa melitta': 'Healthcare',
    'korian': 'Healthcare',
  },
  // Note: fund slug is 'bu' (AIFI_NAME_OVERRIDES maps "BU" → "BU", not "BU Italy")
  'bu': {
    'systabuild software group': 'Technology',
    'relatech': 'Technology',
    'egroup': 'Technology',
    'onlineprinters': 'Technology',
    'synava': 'Technology',
    // Erik Damgaard, Markus Schyboll, Patrick Theobald, Tony Quinlan, Walter Meyer
    // are garbage scrape artifacts (person names, not portfolio companies)
  },
  'narval-investimenti': {
    'sied': 'Industrial',
    'arbo': 'Industrial',
    'permicro': 'Financial Services',
    'solar investment group': 'Energy',
    'farmagora': 'Healthcare',
    'farmagor\u00e0': 'Healthcare',
    'twinset': 'Consumer',
    'industrial investments': 'Financial Services',
  },

  // ─── Phase 3: Additional funds ────────────────────────────────────

  'pm-partners-sgr': {
    'bia': 'Food & Beverage',
    'montanaspa': 'Industrial',
    'cognitive': 'Technology',
    'italtergi': 'Energy',
    'finlogic': 'Technology',
    'cosmelux': 'Consumer',
    'cytech': 'Technology',
    'omt': 'Industrial',
    'plastiape': 'Industrial',
    'monviso': 'Food & Beverage',
    'la patria': 'Food & Beverage',
    'relevi': 'Consumer',
    'emmeti': 'Industrial',
    'maccorp': 'Business Services',
    'elemaster': 'Industrial',
    'vimec': 'Healthcare',
    'argenta': 'Business Services',
    'alfatherm': 'Industrial',
    'aeb': 'Technology',
    'aive': 'Industrial',
    'idra': 'Industrial',
    'eco': 'Industrial',
  },
  'consilium-sgr': {
    'faccin': 'Industrial',
    'gruppo manifatture italiane': 'Consumer',
    'dino corsini': 'Industrial',
    'music center': 'Consumer',
    'fonderia boccacci': 'Industrial',
    'cela': 'Industrial',
    'celli group': 'Industrial',
    'gelit': 'Food & Beverage',
    'macron': 'Consumer',
    'rollon': 'Industrial',
    'gruppo douglas': 'Consumer',
    'nutkao': 'Food & Beverage',
    'ion trading': 'Technology',
    'marsilli': 'Industrial',
    'mfu': 'Industrial',
    'bouty healthcare': 'Healthcare',
    'bbi electric': 'Industrial',
    'gmm': 'Healthcare',
    'manifattura riese': 'Consumer',
    'tucano urbano': 'Consumer',
    'de fonseca': 'Consumer',
  },
  'azimut-libera-impresa-sgr': {
    'acque minerali d\'italia s.p.a.': 'Food & Beverage',
    'corvallis holding s.p.a': 'Technology',
    'i.co.p. s.p.a': 'Infrastructure',
    'lima corporate s.p.a': 'Healthcare',
    'renco group s.p.a.': 'Industrial',
    'isoclima s.p.a.': 'Industrial',
    'ocs s.p.a.': 'Business Services',
    'italcer s.p.a.': 'Industrial',
    'vega carburanti s.p.a.': 'Energy',
    'gwc italia s.p.a.': 'Industrial',
    'iaf network s.r.l.': 'Business Services',
    'dgs s.p.a.': 'Technology',
  },
  'alkemia-sgr': {
    'agricooltur': 'Food & Beverage',
    'codemotion': 'Technology',
    'contents': 'Technology',
    'convivio s.p.a': 'Food & Beverage',
    'ermes browser security': 'Technology',
    'hlpy': 'Technology',
    'redelfi energy': 'Energy',
    'tecno group': 'Industrial',
  },

  // ─── Tier 1 optimization batch 1 ──────────────────────────────────

  'tikehau-capital': {
    'lebronze alloys': 'Industrial',
    'adit': 'Technology',
    'agora': 'Media & Telecom',
    'antas': 'Industrial',
    'bastide': 'Healthcare',
    'boma': 'Real Estate',
    'brouwerij martens': 'Food & Beverage',
    'calisto': 'Industrial',
    'cebat': 'Industrial',
    'cegedim': 'Healthcare',
    'cream': 'Consumer',
    'crystal': 'Consumer',
  },
  'key-capital': {
    'sowidely': 'Technology',
    'nimai': 'Financial Services',
    'cesarine': 'Food & Beverage',
    'leafspace': 'Technology',
    'swascan': 'Technology',
    'checkbonus': 'Financial Services',
    'musicraiser': 'Media & Telecom',
    'lifelearning': 'Technology',
  },
  'zest-group': {
    'gevi': 'Food & Beverage',
    'elai': 'Industrial',
    'sartiq': 'Consumer',
    'apside': 'Technology',
    'open t': 'Technology',
  },
};

// ─── Main ───────────────────────────────────────────────────────────

interface PortfolioEntry {
  name: string;
  sector: string | null;
  [key: string]: unknown;
}

interface PortfolioFile {
  fund_portfolios: Record<string, PortfolioEntry[]>;
}

function main() {
  console.log('Enriching portfolio sectors...\n');

  const data: PortfolioFile = JSON.parse(readFileSync(PORTFOLIO_PATH, 'utf-8'));
  let totalUpdated = 0;
  let totalSkipped = 0;
  let totalNotFound = 0;

  for (const [fundSlug, sectorMap] of Object.entries(SECTOR_MAPS)) {
    const companies = data.fund_portfolios[fundSlug];
    if (!companies) {
      console.log(`  [WARN] Fund ${fundSlug} not found in portfolio_items.json`);
      continue;
    }

    let fundUpdated = 0;
    let fundSkipped = 0;
    let fundNotFound = 0;

    for (const company of companies) {
      if (company.sector != null) {
        fundSkipped++;
        continue;
      }

      const key = company.name.toLowerCase().trim();
      const sector = sectorMap[key];
      if (sector) {
        company.sector = sector;
        fundUpdated++;
      } else {
        fundNotFound++;
        console.log(`  [MISS] ${fundSlug}: "${company.name}" not in sector map`);
      }
    }

    console.log(`  ${fundSlug}: ${fundUpdated} updated, ${fundSkipped} already had sectors, ${fundNotFound} not in map`);
    totalUpdated += fundUpdated;
    totalSkipped += fundSkipped;
    totalNotFound += fundNotFound;
  }

  writeFileSync(PORTFOLIO_PATH, JSON.stringify(data, null, 2) + '\n');
  console.log(`\nTotal: ${totalUpdated} sectors added, ${totalSkipped} preserved, ${totalNotFound} unmatched`);
}

main();
