/**
 * Seed script for Fundradar
 *
 * Sprint 0: Created mock database from hardcoded data.
 * Sprint 1: Creates database from parsed PEM data (investors + deals).
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import type { Fund, Signal, PemManifest, Deal, FundCategory } from '@fundradar/shared';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');

// Explicit fund classifications from classification-urls.md
// Key is normalized slug or name fragment for matching
const EXPLICIT_CLASSIFICATIONS: Record<string, FundCategory> = {
  // Multi-Strategy (Global Alt Managers)
  'blackstone': 'multi_strategy',
  'kkr': 'multi_strategy',
  'investindustrial': 'pe',
  'oakley capital': 'pe',
  'towerbrook': 'pe',
  'astorg': 'pe',
  'perwyn': 'pe',
  'apollo': 'multi_strategy',
  'carlyle': 'multi_strategy',
  'ares': 'multi_strategy',
  'bain capital': 'multi_strategy',
  'cvc capital': 'multi_strategy',
  'ardian': 'multi_strategy',
  'eqt': 'multi_strategy',
  'partners group': 'multi_strategy',
  'tikehau': 'multi_strategy',
  'oaktree': 'multi_strategy',
  'h.i.g.': 'multi_strategy',
  'hig capital': 'multi_strategy',
  'investcorp': 'multi_strategy',
  'clessidra-sgr': 'multi_strategy',
  'quadrivio': 'multi_strategy',
  'green arrow': 'multi_strategy',
  'tages capital': 'multi_strategy',
  'azimut libera': 'multi_strategy',
  'dea capital': 'multi_strategy',
  'centerbridge': 'multi_strategy',
  'cerberus': 'multi_strategy',
  'eurazeo': 'multi_strategy',
  'pollen street': 'multi_strategy',
  'attestor': 'multi_strategy',
  'cathay capital': 'multi_strategy',
  'alchemy': 'multi_strategy',
  'icg': 'multi_strategy',
  'intermediate capital': 'multi_strategy',
  'lgt capital': 'multi_strategy',
  'riverrock': 'multi_strategy',
  'brookfield': 'multi_strategy',
  'bdt': 'multi_strategy',
  'viking global': 'multi_strategy',
  'swen capital': 'multi_strategy',
  'fondo italiano d\'investimento': 'multi_strategy',
  'fondo italiano': 'multi_strategy',
  'eos investment': 'multi_strategy',
  'equita capital': 'multi_strategy',
  'alternative capital partners': 'multi_strategy',
  'capital dynamics': 'multi_strategy',
  'bnp paribas capital': 'multi_strategy',
  'davidson kempner': 'multi_strategy',
  'suma capital': 'multi_strategy',
  'vinci partners': 'multi_strategy',

  // Infrastructure
  'f2i-sgr': 'infra',
  'dif capital': 'infra',
  'macquarie': 'infra',
  'meridiam': 'infra',
  'infravia': 'infra',
  'i squared': 'infra',
  'icon infrastructure': 'infra',
  'cube infrastructure': 'infra',
  'equitix': 'infra',
  'glennmont': 'infra',
  'ifm investors': 'infra',
  'pioneer point': 'infra',
  'asterion': 'infra',
  'copenhagen infrastructure': 'infra',
  'amber infrastructure': 'infra',
  'aquila': 'infra',
  'stonepeak': 'infra',
  'antin': 'infra',
  'fiee': 'infra',
  'nexta capital': 'infra',
  'sosteneo': 'infra',
  'quercus': 'infra',
  'helios energy': 'infra',
  'energy infrastructure': 'infra',
  'serena industrial': 'infra',
  'obton': 'infra',
  'ram energy': 'infra',
  'spin energy': 'infra',
  'vtti': 'infra',
  'ikav': 'infra',
  'marinedi': 'infra',
  'blue elephant': 'infra',
  'agreencapital': 'infra',
  'exus': 'infra',

  // Venture Capital
  'speedinvest': 'vc',
  'amadeus capital': 'vc',
  'paladin capital': 'vc',
  'insight partners': 'vc',
  'capitalg': 'vc',
  'oxford capital': 'vc',
  'innovative-rfk': 'vc',
  'bemycompany': 'vc',
  'clave capital': 'vc',
  'da vinci': 'vc',
  'miton': 'vc',
  'newseed': 'vc',
  'xpv water': 'vc',
  'principia sgr': 'vc',
  'axon partners': 'vc',
  'lmdv capital': 'vc',
  'lian group': 'vc',
  'first fellow': 'vc',
  'zernike': 'vc',
  'mps venture': 'vc',
  'wise venture': 'vc',

  // Holdings / Family Office
  'italmobiliare': 'holdings',
  'tamburi': 'holdings',
  'tip': 'holdings',
  'exor': 'holdings',
  'edizione': 'holdings',
  'mittel': 'holdings',
  'nuo capital': 'holdings',
  'pargesa': 'holdings',
  'gbl': 'holdings',
  'altamir': 'holdings',
  'latour': 'holdings',
  'nordstjernan': 'holdings',
  'lifco': 'holdings',
  'indutrade': 'holdings',
  'cobepa': 'holdings',
  'fosun': 'holdings',
  'h14': 'holdings',
  'aimia': 'holdings',
  'dentressangle': 'holdings',
  'verlinvest': 'holdings',
  'ion group': 'holdings',
  'kayak': 'holdings',
  'riello investimenti': 'holdings',
  'uturn investments': 'holdings',
  'fidim': 'holdings',
  'fa investments': 'holdings',
  'lamse': 'holdings',
  'margherita': 'holdings',
  'red circle': 'holdings',
  'cherry bay': 'holdings',
  'carisma': 'holdings',
  'visconti capital': 'holdings',
  'tangor capital': 'holdings',
  'seta holding': 'holdings',
  '7-industries': 'holdings',
  'stena adactum': 'holdings',
  'cleon capital': 'holdings',
  'mega holding': 'holdings',
  'certina': 'holdings',
  'dacke industri': 'holdings',
  'bgroup': 'holdings',
  'cip merchant': 'holdings',
  'hind': 'holdings',
  'lfg holding': 'holdings',
  'athena holding': 'holdings',
  'finvacchi': 'holdings',
  'sammontana': 'holdings',
  'blackwood': 'holdings',
  'petplus': 'holdings',
  'nessi': 'holdings',
  'worxinvest': 'holdings',
  'verteq': 'holdings',
  'omnia partners': 'holdings',
  'esperia investor': 'holdings',
  'ethica group': 'holdings',
  'marfin': 'holdings',

  // Debt / Credit
  'three hills': 'debt',
  'oxy capital': 'debt',
  'antares capital': 'debt',
  'hps investment': 'debt',
  'arrow global': 'debt',
  'blantyre': 'debt',
  'hutton collins': 'debt',
  'bravo capital': 'debt',
  'north wall': 'debt',
  'fortelus': 'debt',
  'axiom': 'debt',
  'fitzwalter': 'debt',
  'eso capital': 'debt',
  'eiffel investment': 'debt',
  'emisys': 'debt',
  'advicorp': 'debt',
  'pillarstone': 'debt',
  'muzinich': 'debt',
  'anthilia': 'debt',

  // Sovereign / Development
  'cdp equity': 'sovereign',
  'bpifrance': 'sovereign',
  'invitalia': 'sovereign',
  'adia': 'sovereign',
  'cdpq': 'sovereign',
  'psp investments': 'sovereign',
  'eib': 'sovereign',

  // Banks
  'amco': 'bank',
  'illimity': 'bank',
  'mediobanca': 'bank',
  'banca ifis': 'bank',
  'credem': 'bank',
  'deutsche bank': 'bank',
  'moelis': 'bank',
  'rothschild': 'bank',
  'bnl': 'bank',
  'banca profilo': 'bank',
  'mps capital services': 'bank',
  'finint': 'bank',
  'sella sgr': 'bank',
  'bcc risparmio': 'bank',
  'fineco capital': 'bank',

  // Asset Managers
  'nuveen': 'asset_manager',
  'neuberger berman': 'asset_manager',
  'bnp paribas am': 'asset_manager',
  'dws': 'asset_manager',
  'schroders': 'asset_manager',
  'algebris': 'asset_manager',
  'azimut': 'asset_manager',
  'eurizon': 'asset_manager',
  'amundi': 'asset_manager',
  'anima sgr': 'asset_manager',
  'aviva investors': 'asset_manager',
  'bestinver': 'asset_manager',
  'goldman sachs am': 'asset_manager',
  'td asset management': 'asset_manager',
  'bmo global': 'asset_manager',
  'kairos partners': 'asset_manager',
  'banor': 'asset_manager',
  'arca fondi': 'asset_manager',
  'anima alternative': 'asset_manager',
  'copernicus': 'asset_manager',
  'sagitta sgr': 'asset_manager',
  'twenty first capital': 'asset_manager',
  'mirae asset': 'asset_manager',
  'mc square': 'asset_manager',

  // Real Estate
  'patrizia': 'real_estate',
  'hines': 'real_estate',
  'castello sgr': 'real_estate',
  'orange capital': 'real_estate',
  'augusta capital': 'real_estate',

  // Fund of Funds / Secondaries
  'perennius': 'fund_of_funds',
  'compass partners': 'fund_of_funds',
  'headway capital': 'fund_of_funds',
};

// Keyword patterns for fallback classification (word-boundary aware)
const CATEGORY_KEYWORDS: Record<FundCategory, string[]> = {
  vc: ['venture', 'startup', 'seed'],
  infra: ['infrastructure', 'infra', 'energy', 'renewable'],
  debt: ['debt', 'credit', 'lending', 'mezzanine'],
  holdings: ['holding', 'family office'],
  growth: ['growth equity'],
  real_estate: ['real estate', 'immobili', 'property'],
  fund_of_funds: ['fund of funds', 'fof'],
  multi_strategy: [],
  sovereign: ['sovereign', 'development bank'],
  bank: [],
  asset_manager: ['asset manager', 'wealth management'],
  pe: [],
  unknown: [],
};

function normalizeForMatching(text: string): string {
  return text
    .toLowerCase()
    .replace(/[''`]/g, "'")
    .replace(/[-_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function classifyFund(name: string, slug: string): FundCategory {
  const normalizedName = normalizeForMatching(name);
  const normalizedSlug = normalizeForMatching(slug);
  const searchText = `${normalizedName} ${normalizedSlug}`;

  // First, check explicit mappings (highest priority)
  for (const [key, category] of Object.entries(EXPLICIT_CLASSIFICATIONS)) {
    const normalizedKey = normalizeForMatching(key);
    if (
      searchText.includes(normalizedKey) ||
      normalizedName.startsWith(normalizedKey) ||
      normalizedSlug.startsWith(normalizedKey)
    ) {
      return category;
    }
  }

  // Second, check keyword patterns with word boundaries
  for (const [category, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
    if (category === 'pe' || category === 'unknown' || keywords.length === 0) continue;

    for (const keyword of keywords) {
      // Use word boundary matching to avoid "cvc" matching "vc"
      const regex = new RegExp(`\\b${keyword}\\b`, 'i');
      if (regex.test(searchText)) {
        return category as FundCategory;
      }
    }
  }

  // Default to PE for unclassified funds (most Italian funds are PE)
  return 'pe';
}

// Parsed investor from PEM
interface PemInvestor {
  slug: string;
  name: string;
  deal_count: number;
  first_seen_year: number;
}

interface PemInvestorsFile {
  generated_at: string;
  investors: PemInvestor[];
}

interface PemDealsFile {
  generated_at: string;
  deals: Deal[];
}

interface Database {
  generated_at: string;
  pem_manifest: PemManifest | null;
  funds: Fund[];
  deals: Deal[];
  signals: Signal[];
}

function createFundFromInvestor(investor: PemInvestor, index: number): Fund {
  const now = new Date().toISOString();
  const cleanName = investor.name.replace(/\n/g, ' '); // Clean up newlines in names
  const category = classifyFund(cleanName, investor.slug);

  return {
    id: `fund-${index + 1}`,
    slug: investor.slug,
    name: cleanName,
    category,
    hq_city: null, // Will be enriched later
    hq_region: null,
    website: null,
    strategy_tags: category === 'vc' ? ['VC'] : ['PE'], // Tag based on category
    sector_tags: [],
    description: null,
    created_at: now,
    updated_at: now,
  };
}

async function seed() {
  console.log('Fundradar Seed Script (Sprint 1)');
  console.log('================================\n');

  const dataDir = join(projectRoot, 'data');
  const derivedDir = join(dataDir, 'derived');
  const manifestPath = join(derivedDir, 'pem_manifest.json');
  const investorsPath = join(derivedDir, 'pem_investors.json');
  const dealsPath = join(derivedDir, 'pem_deals.json');
  const dbPath = join(dataDir, 'db.json');

  // Load PEM manifest
  let pemManifest: PemManifest | null = null;
  if (existsSync(manifestPath)) {
    try {
      pemManifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
      console.log(`Loaded PEM manifest with ${pemManifest?.entries.length ?? 0} entries`);
    } catch {
      console.log('Warning: Could not parse PEM manifest');
    }
  }

  // Load parsed investors
  let funds: Fund[] = [];
  if (existsSync(investorsPath)) {
    try {
      const investorsData: PemInvestorsFile = JSON.parse(readFileSync(investorsPath, 'utf-8'));
      funds = investorsData.investors.map((inv, i) => createFundFromInvestor(inv, i));
      console.log(`Created ${funds.length} funds from PEM investors`);
    } catch (e) {
      console.log('Warning: Could not parse PEM investors:', e);
    }
  } else {
    console.log('No PEM investors found. Run `pnpm worker:ingest` first.');
  }

  // Load parsed deals
  let deals: Deal[] = [];
  if (existsSync(dealsPath)) {
    try {
      const dealsData: PemDealsFile = JSON.parse(readFileSync(dealsPath, 'utf-8'));
      deals = dealsData.deals;
      console.log(`Loaded ${deals.length} deals from PEM`);
    } catch (e) {
      console.log('Warning: Could not parse PEM deals:', e);
    }
  }

  // Create signals from deals (one signal per deal as "deal_announced")
  // PEM official source URL
  const PEM_SOURCE_URL = 'https://www.liucbs.it/osservatori/private-equity-monitor-pem/';

  const signals: Signal[] = deals.slice(0, 50).map((deal, i) => ({
    id: `signal-${i + 1}`,
    fund_id: `fund-${funds.findIndex((f) => f.slug === deal.lead_investor_slug) + 1}`,
    signal_type: 'deal_announced' as const,
    title: `Investment in ${deal.target_company}`,
    what_changed: `${deal.lead_investor} ${deal.investment_stage ? `made a ${deal.investment_stage} investment` : 'invested'} in ${deal.target_company}${deal.region ? ` (${deal.region})` : ''}.`,
    source_url: PEM_SOURCE_URL,
    source_name: 'PEM (Private Equity Monitor)',
    source_url_status: 'ok' as const,
    published_at: `${deal.source_year}-01-01`, // Year only known
    observed_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
  }));

  // Create the database
  const db: Database = {
    generated_at: new Date().toISOString(),
    pem_manifest: pemManifest,
    funds,
    deals,
    signals,
  };

  // Ensure data directory exists
  if (!existsSync(dataDir)) {
    mkdirSync(dataDir, { recursive: true });
  }

  // Safety guard: refuse to overwrite a curated db.json (>100 funds with AUM data)
  if (existsSync(dbPath)) {
    try {
      const existing = JSON.parse(readFileSync(dbPath, 'utf-8'));
      const fundsWithAum = (existing.funds || []).filter((f: any) => f.aum_eur);
      if (fundsWithAum.length > 50) {
        console.error(`\n  ABORT: ${dbPath} already contains ${existing.funds.length} curated funds (${fundsWithAum.length} with AUM).`);
        console.error('  The seed script would overwrite this with PEM stubs. Use --force to override.\n');
        if (!process.argv.includes('--force')) {
          process.exit(1);
        }
        console.warn('  --force flag detected, overwriting...\n');
      }
    } catch { /* file exists but can't be parsed — safe to overwrite */ }
  }

  // Write database
  writeFileSync(dbPath, JSON.stringify(db, null, 2));

  console.log('\nDatabase created:');
  console.log(`  - ${db.funds.length} funds`);
  console.log(`  - ${db.deals.length} deals`);
  console.log(`  - ${db.signals.length} signals (sample)`);
  console.log(`\nWritten to: ${dbPath}`);
}

seed().catch((err) => {
  console.error('Seed failed:', err);
  process.exit(1);
});
