import { describe, expect, it } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import { canonicalizeSectorTag, fundSectorGroups } from './sectorGroups';
import { buildSectorGroupCounts, matchesSectorGroupFilter, type FilterableFund } from './fundFilters';

describe('sector tag canonicalization', () => {
  it('maps infrastructure variants to transport/logistics taxonomy', () => {
    expect(canonicalizeSectorTag('Infrastructure / Aviation')).toBe('Transportation & Logistics');
    expect(canonicalizeSectorTag('Infrastructure / Maritime')).toBe('Transportation & Logistics');
    expect(canonicalizeSectorTag('Infrastructure')).toBe('Transportation & Logistics');
  });

  it('maps other known variants into canonical tags', () => {
    expect(canonicalizeSectorTag('Industrial')).toBe('Industrial Manufacturing');
    expect(canonicalizeSectorTag('Information & Telecom')).toBe('Telecommunications');
    expect(canonicalizeSectorTag('Financials')).toBe('Financial Services');
  });
});

describe('sector group mapping with aliases', () => {
  const funds: FilterableFund[] = [
    { category: 'infra', sector_tags: ['Infrastructure / Aviation'] },
    { category: 'pe', sector_tags: ['Industrial'] },
    { category: 'vc', sector_tags: ['Information & Telecom'] },
  ];

  it('returns grouped chips for alias-only sector tags', () => {
    expect(fundSectorGroups(['Infrastructure / Maritime'])).toEqual(['Transport & Logistics']);
    expect(fundSectorGroups(['Industrial'])).toEqual(['Industrial']);
    expect(fundSectorGroups(['Information & Telecom'])).toEqual(['Technology']);
  });

  it('counts sector groups via canonicalized tags', () => {
    const counts = buildSectorGroupCounts(funds);
    expect(counts.get('Transport & Logistics')).toBe(1);
    expect(counts.get('Industrial')).toBe(1);
    expect(counts.get('Technology')).toBe(1);
  });

  it('matches sector filters via canonicalized tags', () => {
    expect(matchesSectorGroupFilter(funds[0], 'Transport & Logistics')).toBe(true);
    expect(matchesSectorGroupFilter(funds[1], 'Industrial')).toBe(true);
    expect(matchesSectorGroupFilter(funds[2], 'Technology')).toBe(true);
  });

  it('maps all current portfolio-derived sectors to a sector group', () => {
    const portfolioPath = join(process.cwd(), '..', '..', 'data', 'derived', 'portfolio_items.json');
    const data = JSON.parse(readFileSync(portfolioPath, 'utf-8'));
    const unmapped = new Set<string>();

    for (const items of Object.values<any>(data.fund_portfolios || {})) {
      for (const item of items || []) {
        if (item.status && item.status !== 'current') continue;
        const sector = typeof item.sector === 'string' ? item.sector.trim() : '';
        if (!sector) continue;
        if (fundSectorGroups([sector]).length === 0) {
          unmapped.add(sector);
        }
      }
    }

    expect(Array.from(unmapped).sort()).toEqual([]);
  });
});
