import type { FundCategory, Office } from '@fundradar/shared';
import { SECTOR_GROUPS, SECTOR_TO_GROUP, canonicalizeSectorTag } from './sectorGroups';
import { ITALIAN_CITIES } from './italianCompany';

export interface FilterableFund {
  category: FundCategory;
  sector_tags?: string[];
  offices?: Office[];
  hq_city?: string | null;
  hq_region?: string | null;
}

export interface FundFilterCatalog {
  categories: FundCategory[];
  categoryCounts: Map<FundCategory, number>;
  sectors: string[];
  hqCountries: string[];
}

const COUNTRY_ALIASES: Record<string, string> = {
  italy: 'Italy',
  italia: 'Italy',
  usa: 'USA',
  'u s a': 'USA',
  'u.s.a': 'USA',
  us: 'USA',
  'united states': 'USA',
  'united states of america': 'USA',
  uk: 'UK',
  'u k': 'UK',
  'u.k': 'UK',
  'united kingdom': 'UK',
  england: 'UK',
  britain: 'UK',
  france: 'France',
  germany: 'Germany',
  spain: 'Spain',
  switzerland: 'Switzerland',
  austria: 'Austria',
  netherlands: 'Netherlands',
  belgium: 'Belgium',
  luxembourg: 'Luxembourg',
  sweden: 'Sweden',
  denmark: 'Denmark',
  norway: 'Norway',
  finland: 'Finland',
  ireland: 'Ireland',
  portugal: 'Portugal',
  poland: 'Poland',
  czechia: 'Czechia',
  'czech republic': 'Czechia',
  canada: 'Canada',
  australia: 'Australia',
  japan: 'Japan',
  singapore: 'Singapore',
  china: 'China',
  uae: 'UAE',
  'united arab emirates': 'UAE',
};

const FOREIGN_CITY_TO_COUNTRY: Record<string, string> = {
  london: 'UK',
  jersey: 'UK',
  'new york': 'USA',
  'los angeles': 'USA',
  boston: 'USA',
  'san francisco': 'USA',
  miami: 'USA',
  greenwich: 'USA',
  amsterdam: 'Netherlands',
  madrid: 'Spain',
  paris: 'France',
  parigi: 'France',
  luxembourg: 'Luxembourg',
  stockholm: 'Sweden',
  brussels: 'Belgium',
  bruxelles: 'Belgium',
  lisbon: 'Portugal',
  lisboa: 'Portugal',
  frankfurt: 'Germany',
  'frankfurt am main': 'Germany',
  munich: 'Germany',
  zug: 'Switzerland',
  baar: 'Switzerland',
  zurich: 'Switzerland',
  geneva: 'Switzerland',
  dublin: 'Ireland',
  oslo: 'Norway',
  copenhagen: 'Denmark',
  helsinki: 'Finland',
  warsaw: 'Poland',
};


function normalizeToken(value: string | null | undefined): string {
  return (value || '')
    .trim()
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[._]/g, ' ')
    .replace(/\s+/g, ' ');
}

function normalizeCountry(value: string | null | undefined): string | null {
  const key = normalizeToken(value);
  if (!key) return null;
  if (COUNTRY_ALIASES[key]) return COUNTRY_ALIASES[key];

  // Fallback title-case for unknown-but-present country values.
  return key
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ');
}

function getExplicitHqOfficeCountry(offices: Office[] | undefined): string | null {
  if (!offices || offices.length === 0) return null;
  const hq = offices.find((o) => o.is_hq && typeof o.country === 'string' && o.country.trim());
  return hq ? normalizeCountry(hq.country) : null;
}

function getFirstOfficeCountry(offices: Office[] | undefined): string | null {
  if (!offices || offices.length === 0) return null;
  const first = offices.find((o) => typeof o.country === 'string' && o.country.trim());
  return first ? normalizeCountry(first.country) : null;
}

export function deriveFundHqCountry(fund: FilterableFund): string | null {
  // 1. Explicit is_hq office
  const hqOfficeCountry = getExplicitHqOfficeCountry(fund.offices);
  if (hqOfficeCountry) return hqOfficeCountry;

  // 2. hq_city — checked before non-HQ office fallback so an explicit city field wins
  const cityKey = normalizeToken(fund.hq_city);
  if (cityKey && FOREIGN_CITY_TO_COUNTRY[cityKey]) {
    return FOREIGN_CITY_TO_COUNTRY[cityKey];
  }
  if (cityKey && ITALIAN_CITIES.has(cityKey)) {
    return 'Italy';
  }

  // 3. hq_region — checked before first-office fallback so an explicit region field
  //    wins over a stale Italian office entry in offices[]
  const regionCountry = normalizeCountry(fund.hq_region);
  if (regionCountry) return regionCountry;

  // 4. First office with any country (last resort)
  const firstOfficeCountry = getFirstOfficeCountry(fund.offices);
  if (firstOfficeCountry) return firstOfficeCountry;

  return null;
}

export function matchesHqCountryFilter(fund: FilterableFund, countryFilter: string | 'all'): boolean {
  if (countryFilter === 'all') return true;
  const hqCountry = deriveFundHqCountry(fund);
  return hqCountry === countryFilter;
}

/** Build counts per sector group from a list of funds */
export function buildSectorGroupCounts(funds: FilterableFund[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const fund of funds) {
    const seen = new Set<string>();
    for (const tag of fund.sector_tags || []) {
      const group = SECTOR_TO_GROUP[canonicalizeSectorTag(tag)];
      if (group && !seen.has(group)) {
        seen.add(group);
        counts.set(group, (counts.get(group) || 0) + 1);
      }
    }
  }
  return counts;
}

/** Returns sector group names ordered by the SECTOR_GROUPS definition (stable order) */
export function getSectorGroupOptions(counts: Map<string, number>): { value: string; label: string; count: number }[] {
  return SECTOR_GROUPS
    .filter(g => (counts.get(g.name) || 0) > 0)
    .map(g => ({ value: g.name, label: g.name, count: counts.get(g.name) || 0 }));
}

/** Check if a fund matches a sector group filter */
export function matchesSectorGroupFilter(fund: FilterableFund, groupName: string | 'all'): boolean {
  if (groupName === 'all') return true;
  const group = SECTOR_GROUPS.find(g => g.name === groupName);
  if (!group) return false;
  return (fund.sector_tags || []).some(tag => group.members.includes(canonicalizeSectorTag(tag)));
}

export function buildFundFilterCatalog<T extends FilterableFund>(funds: T[]): FundFilterCatalog {
  const categoryCounts = new Map<FundCategory, number>();
  const sectors = new Set<string>();
  const hqCountryCounts = new Map<string, number>();

  for (const fund of funds) {
    categoryCounts.set(fund.category, (categoryCounts.get(fund.category) || 0) + 1);
    for (const sector of fund.sector_tags || []) {
      sectors.add(sector);
    }

    const hqCountry = deriveFundHqCountry(fund);
    if (hqCountry) hqCountryCounts.set(hqCountry, (hqCountryCounts.get(hqCountry) || 0) + 1);
  }

  const categories = Array.from(categoryCounts.keys()).sort((a, b) => {
    const diff = (categoryCounts.get(b) || 0) - (categoryCounts.get(a) || 0);
    if (diff !== 0) return diff;
    return a.localeCompare(b);
  });

  const sortedCountries = Array.from(hqCountryCounts.keys()).sort((a, b) => {
    if (a === 'Italy') return -1;
    if (b === 'Italy') return 1;
    const diff = (hqCountryCounts.get(b) || 0) - (hqCountryCounts.get(a) || 0);
    if (diff !== 0) return diff;
    return a.localeCompare(b);
  });

  return {
    categories,
    categoryCounts,
    sectors: Array.from(sectors).sort(),
    hqCountries: sortedCountries,
  };
}
