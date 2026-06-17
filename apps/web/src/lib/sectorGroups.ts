/**
 * Sector group mapping: collapses 30-sector taxonomy into 10 groups for filter UI.
 * The underlying sector_tags in db.json stay unchanged — this is UI-only grouping.
 */

export interface SectorGroup {
  name: string;
  members: string[];
  color: { bg: string; text: string };
}

export const SECTOR_GROUPS: SectorGroup[] = [
  {
    name: 'Technology',
    members: ['Technology', 'Software', 'Telecommunications'],
    color: { bg: '#e8eaf6', text: '#283593' },
  },
  {
    name: 'Healthcare',
    members: ['Healthcare', 'Biotech & Pharma'],
    color: { bg: '#e0f2f1', text: '#00695c' },
  },
  {
    name: 'Industrial',
    members: ['Industrial Manufacturing', 'Automotive', 'Aerospace & Defense', 'Chemicals', 'Mining & Metals', 'Packaging'],
    color: { bg: '#eceff1', text: '#263238' },
  },
  {
    name: 'Consumer & Retail',
    members: ['Consumer Goods', 'Retail', 'Fashion & Luxury'],
    color: { bg: '#ffebee', text: '#c62828' },
  },
  {
    name: 'Food & Agriculture',
    members: ['Food & Beverage', 'Agriculture', 'Hospitality & Tourism'],
    color: { bg: '#fff3e0', text: '#bf360c' },
  },
  {
    name: 'Business Services',
    members: ['Professional Services', 'Financial Services', 'Insurance'],
    color: { bg: '#eceff1', text: '#455a64' },
  },
  {
    name: 'Energy & Environment',
    members: ['Energy', 'Renewable Energy', 'Environmental Services', 'Waste Management', 'Water & Utilities'],
    color: { bg: '#e8f5e9', text: '#2e7d32' },
  },
  {
    name: 'Real Estate & Construction',
    members: ['Real Estate', 'Construction'],
    color: { bg: '#efebe9', text: '#4e342e' },
  },
  {
    name: 'Media & Education',
    members: ['Media & Entertainment', 'Education'],
    color: { bg: '#f3e5f5', text: '#6a1b9a' },
  },
  {
    name: 'Transport & Logistics',
    members: ['Transportation & Logistics'],
    color: { bg: '#e0f2f1', text: '#004d40' },
  },
];

const NORMALIZE_TOKEN_RE = /[^a-z0-9]+/g;

function normalizeSectorToken(value: string): string {
  return value.toLowerCase().trim().replace(NORMALIZE_TOKEN_RE, ' ').replace(/\s+/g, ' ').trim();
}

/** Reverse map: individual sector → group name */
export const SECTOR_TO_GROUP: Record<string, string> = {};
for (const group of SECTOR_GROUPS) {
  for (const member of group.members) {
    SECTOR_TO_GROUP[member] = group.name;
  }
}

const CANONICAL_BY_NORMALIZED: Record<string, string> = {};
for (const member of Object.keys(SECTOR_TO_GROUP)) {
  CANONICAL_BY_NORMALIZED[normalizeSectorToken(member)] = member;
}

// Exact aliases for frequent upstream variants.
const SECTOR_TAG_ALIASES: Record<string, string> = {
  'energy & environment': 'Energy',
  'business services': 'Professional Services',
  'business intelligence': 'Software',
  'financials': 'Financial Services',
  'fintech': 'Financial Services',
  'medtech': 'Healthcare',
  'healthtech': 'Healthcare',
  'edtech': 'Education',
  'digital transformation': 'Technology',
  'decision intelligence': 'Software',
  'e commerce': 'Retail',
  'fashion': 'Fashion & Luxury',
  'textiles': 'Fashion & Luxury',
  'furniture': 'Consumer Goods',
  'cosmetics': 'Consumer Goods',
  'beauty': 'Consumer Goods',
  'beauty cosmetics': 'Consumer Goods',
  'nutraceuticals cosmetics': 'Healthcare',
  'food': 'Food & Beverage',
  'agrifood': 'Food & Beverage',
  'agri food': 'Food & Beverage',
  'ict': 'Telecommunications',
  'information telecom': 'Telecommunications',
  'information technology': 'Technology',
  'cybersecurity': 'Software',
  'artificial intelligence': 'Software',
  'deep tech': 'Technology',
  'big data': 'Software',
  'robotics': 'Industrial Manufacturing',
  'industrial': 'Industrial Manufacturing',
  'industrials': 'Industrial Manufacturing',
  'industrial products': 'Industrial Manufacturing',
  'industrial machinery': 'Industrial Manufacturing',
  'industrial technology': 'Industrial Manufacturing',
  'industrial automation': 'Industrial Manufacturing',
  'industrial engineering': 'Industrial Manufacturing',
  'industrial services': 'Industrial Manufacturing',
  'manufacturing': 'Industrial Manufacturing',
  'specialized industrials': 'Industrial Manufacturing',
  'commercial refrigeration': 'Industrial Manufacturing',
  'ceramics': 'Industrial Manufacturing',
  'electronics': 'Industrial Manufacturing',
  'specialty chemicals': 'Chemicals',
  'construction engineering': 'Construction',
  'construction and engineering': 'Construction',
  'mixed use sports': 'Real Estate',
  'residential': 'Real Estate',
  'logistics': 'Transportation & Logistics',
  'transportation': 'Transportation & Logistics',
  'transport and logistics': 'Transportation & Logistics',
  'distribution': 'Transportation & Logistics',
  'service distribution': 'Transportation & Logistics',
  'marine': 'Transportation & Logistics',
  'holding': 'Professional Services',
  'renewables': 'Renewable Energy',
  'solar pv': 'Renewable Energy',
  'electrical equipment ev charging': 'Energy',
  'water treatment': 'Water & Utilities',
  'water infrastructure': 'Water & Utilities',
  'utilities': 'Water & Utilities',
  'blue economy': 'Environmental Services',
  'hospitality': 'Hospitality & Tourism',
  'tourism': 'Hospitality & Tourism',
  'services': 'Professional Services',
  'office': 'Professional Services',
  'semiconductors': 'Technology',
  'video processing': 'Technology',
  'artificial intelligence creative': 'Software',
  'artificial intelligence esg': 'Software',
  'aerospace': 'Aerospace & Defense',
  'space': 'Aerospace & Defense',
  'biotech': 'Biotech & Pharma',
  'biopharmaceuticals': 'Biotech & Pharma',
  'biotechnology': 'Biotech & Pharma',
  'agri tech': 'Agriculture',
  'agribusiness': 'Agriculture',
  'wellness': 'Healthcare',
  'infrastructure': 'Transportation & Logistics',
  'infrastructure aviation': 'Transportation & Logistics',
  'infrastructure maritime': 'Transportation & Logistics',
  'aviation mro': 'Transportation & Logistics',
  'digital enabler': 'Technology',
  'industry 4 0': 'Industrial Manufacturing',
  // Portfolio labels observed from upstream taxonomy drift (EQT / OEP)
  'analytics': 'Software',
  'equality': 'Education',
  'marketing': 'Software',
  'project management sector': 'Software',
  'quantum computing': 'Technology',
  'remote work': 'Software',
  'service': 'Professional Services',
  'social': 'Professional Services',
  'social network': 'Media & Entertainment',
  'sport': 'Media & Entertainment',
  'virtual reality': 'Technology',
  'web development': 'Software',
  'none and region': 'Professional Services',
  's lohmar': 'Industrial Manufacturing',
  // Italian sector labels from AIFI / portfolio data
  'altri settori': 'Professional Services',
  'beni e serv di consumo': 'Consumer Goods',
  'cartotecnica': 'Packaging',
  'dermocosmesi e nutraceutica': 'Healthcare',
  'estensione di assistenza': 'Professional Services',
  'fonderie': 'Industrial Manufacturing',
  'nautica': 'Consumer Goods',
  'nautical': 'Consumer Goods',
  'nutraceutica': 'Healthcare',
  'safety e prevenzione incendi': 'Industrial Manufacturing',
  'scaffalature': 'Industrial Manufacturing',
  // Niche subsectors
  'distribution networks': 'Transportation & Logistics',
  'embedded pc': 'Technology',
  'green space management': 'Environmental Services',
  'led lighting': 'Industrial Manufacturing',
  'mission critical components for aluminium extrusion process': 'Industrial Manufacturing',
  'premium sneakers': 'Fashion & Luxury',
  'tmt': 'Technology',
  // Investment strategy labels (sometimes used as sector in Italian data)
  'artemid senior loans': 'Financial Services',
  'augment knowledge resources': 'Professional Services',
  'elevate quality of life': 'Healthcare',
  'flex equity': 'Financial Services',
  'flex equity mid market': 'Financial Services',
  'growth': 'Financial Services',
  'impact investing': 'Financial Services',
  'private equity': 'Financial Services',
  'venture capital': 'Financial Services',
};

function includesAny(text: string, words: string[]): boolean {
  return words.some((word) => text.includes(word));
}

function inferCanonicalSectorTag(normalized: string): string | null {
  if (!normalized) return null;

  if (SECTOR_TAG_ALIASES[normalized]) return SECTOR_TAG_ALIASES[normalized];
  if (CANONICAL_BY_NORMALIZED[normalized]) return CANONICAL_BY_NORMALIZED[normalized];

  // Strip parenthetical details and retry exact mapping.
  const withoutParens = normalized.replace(/\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim();
  if (withoutParens && SECTOR_TAG_ALIASES[withoutParens]) return SECTOR_TAG_ALIASES[withoutParens];
  if (withoutParens && CANONICAL_BY_NORMALIZED[withoutParens]) return CANONICAL_BY_NORMALIZED[withoutParens];

  // Normalize delimiters so mixed labels like "X / Y" and "X & Y" are handled.
  const normalizedParts = withoutParens
    .replace(/\//g, ' ')
    .replace(/&/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (SECTOR_TAG_ALIASES[normalizedParts]) return SECTOR_TAG_ALIASES[normalizedParts];
  if (CANONICAL_BY_NORMALIZED[normalizedParts]) return CANONICAL_BY_NORMALIZED[normalizedParts];

  if (includesAny(normalizedParts, ['financial', 'fintech', 'payment', 'credit', 'bank', 'insur', 'regtech'])) return 'Financial Services';
  if (includesAny(normalizedParts, ['biotech', 'pharma', 'lifescience', 'life science'])) return 'Biotech & Pharma';
  if (includesAny(normalizedParts, ['health', 'medical', 'medtech', 'caregiving'])) return 'Healthcare';
  if (includesAny(normalizedParts, ['energy', 'renewable', 'cleantech', 'decarbon', 'climate', 'bioenergy', 'transition'])) return 'Energy';
  if (includesAny(normalizedParts, ['water', 'utility', 'waste', 'environment', 'circular'])) return 'Water & Utilities';
  if (includesAny(normalizedParts, ['transport', 'logistic', 'mobility', 'maritime', 'aviation', 'shipping'])) return 'Transportation & Logistics';
  if (includesAny(normalizedParts, ['real estate', 'proptech', 'housing'])) return 'Real Estate';
  if (includesAny(normalizedParts, ['construction', 'building', 'infrastructure', 'materials'])) return 'Construction';
  if (includesAny(normalizedParts, ['food', 'beverage', 'bakery'])) return 'Food & Beverage';
  if (includesAny(normalizedParts, ['agri', 'farming'])) return 'Agriculture';
  if (includesAny(normalizedParts, ['hospitality', 'tourism', 'travel'])) return 'Hospitality & Tourism';
  if (includesAny(normalizedParts, ['media', 'entertainment', 'adtech', 'communication', 'content'])) return 'Media & Entertainment';
  if (includesAny(normalizedParts, ['education', 'edtech'])) return 'Education';
  if (includesAny(normalizedParts, ['software', 'saas', 'cyber', 'ai', 'data', 'ict', 'telecom', 'semiconductor', 'it ', 'it consulting', 'tech'])) return 'Technology';
  if (includesAny(normalizedParts, ['fashion', 'apparel', 'luxury', 'clothing'])) return 'Fashion & Luxury';
  if (includesAny(normalizedParts, ['retail', 'e commerce', 'ecommerce'])) return 'Retail';
  if (includesAny(normalizedParts, ['consumer', 'furniture', 'design', 'pet care', 'hair care', 'footwear', 'boating', 'yachting'])) return 'Consumer Goods';
  if (includesAny(normalizedParts, ['professional', 'consult', 'services', 'hr', 'office', 'certification'])) return 'Professional Services';
  if (includesAny(normalizedParts, ['industrial', 'manufacturing', 'machinery', 'engineering', 'automation', 'robotics', 'mechanic', 'specialized', 'products'])) return 'Industrial Manufacturing';
  if (includesAny(normalizedParts, ['chemical', 'agrochemical'])) return 'Chemicals';
  if (includesAny(normalizedParts, ['automotive'])) return 'Automotive';
  if (includesAny(normalizedParts, ['aerospace', 'defense'])) return 'Aerospace & Defense';
  if (includesAny(normalizedParts, ['packaging', 'labeling'])) return 'Packaging';
  if (includesAny(normalizedParts, ['mining', 'metal'])) return 'Mining & Metals';

  return null;
}

export function canonicalizeSectorTag(tag: string): string {
  const trimmed = tag.trim();
  if (!trimmed) return trimmed;

  const normalized = normalizeSectorToken(trimmed);
  const inferred = inferCanonicalSectorTag(normalized);
  return inferred || trimmed;
}

/** Returns unique group names for a fund's sector_tags */
export function fundSectorGroups(sectorTags: string[]): string[] {
  const groups = new Set<string>();
  for (const tag of sectorTags) {
    const canonical = canonicalizeSectorTag(tag);
    const group = SECTOR_TO_GROUP[canonical];
    if (group) groups.add(group);
  }
  return Array.from(groups);
}

/** Sector tag → canonical group name, or null if unmapped */
export function getSectorGroup(sector: string | null): string | null {
  if (!sector) return null;
  return SECTOR_TO_GROUP[canonicalizeSectorTag(sector)] || null;
}

const DEFAULT_GROUP_COLOR = { bg: '#f5f5f5', text: '#616161' };

/** Group name → color lookup */
export function getSectorGroupColor(groupName: string): { bg: string; text: string } {
  const group = SECTOR_GROUPS.find(g => g.name === groupName);
  return group?.color ?? DEFAULT_GROUP_COLOR;
}
