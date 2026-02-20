'use client';

import React, { useState, useMemo, useEffect } from 'react';
import type { FundCategory } from '@fundradar/shared';
import { FUND_CATEGORY_LABELS } from '@fundradar/shared';
import type { FundSlim } from '@/lib/data';
import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';
import { CATEGORY_COLORS } from '@/lib/colors';
import { deriveFundHqCountry, matchesHqCountryFilter, matchesSectorGroupFilter } from '@/lib/fundFilters';
import { formatAum, findNearestStopIndex } from '@/lib/fundRangeFilters';
import { buildDynamicFundFilterSource } from '@/lib/filterConfig';
import { fundSectorGroups, getSectorGroupColor } from '@/lib/sectorGroups';
import { DualRangeSlider } from '@/components/filters/DualRangeSlider';
import { FilterBar } from '@/components/filters/FilterBar';
import { FilterChips, type ChipItem } from '@/components/filters/FilterChips';
import { FilterDropdown } from '@/components/filters/FilterDropdown';
import { FilterPanel } from '@/components/filters/FilterPanel';

interface FundsTableProps {
  funds: FundSlim[];
  portfolioCompanyNames?: Record<string, string[]>;
  onFilteredFundsChange?: (slugs: string[]) => void;
}

// Short names for mobile display in the Funds in Italy table.
// Use slug keys to avoid punctuation/encoding mismatches in fund names.
const SHORT_FUND_NAMES_BY_SLUG: Record<string, string> = {
  'sviluppo-imprese-centro-italia-sgr': 'Sviluppo Imprese CI',
  'dea-capital-alternative-funds-sgr': 'DeA Capital Alt.',
  'fondo-italiano-d-investimento-sgr': 'Fondo Italiano',
  'alternative-capital-partners-sgr': 'ACP SGR',
  'teamsystem-capital-at-work-sgr': 'TeamSystem CaW',
  'avanzi-etica-sicaf-euveca': 'Avanzi Etica',
  'azimut-libera-impresa-sgr': 'Azimut Libera',
  'cdp-equity': 'CDP Equity',
  'green-arrow-capital-sgr': 'Green Arrow',
  'private-equity-partners': 'PE Partners',
  'riello-investimenti-sgr': 'Riello Inv.',
  'sinloc-investimenti-sgr': 'Sinloc Inv.',
  // Additional long names that can wrap to 3 lines on mobile.
  'mindful-capital': 'Mindful Capital',
};

function getShortName(fund: FundSlim): string {
  return SHORT_FUND_NAMES_BY_SLUG[fund.slug] || fund.name;
}

// Short category labels for mobile
const SHORT_CATEGORY_LABELS: Record<string, string> = {
  'Private Equity': 'PE',
  'Venture Capital': 'VC',
  'Growth Equity': 'Growth',
  'Infrastructure': 'Infra',
  'Private Debt': 'Debt',
  'Real Estate': 'Real Est.',
  'Fund of Funds': 'FoF',
  'Multi-Strategy': 'Multi',
  'Asset Manager': 'Asset Mgr',
};

const ITALIAN_TO_ENGLISH_CITY: Record<string, string> = {
  'Milano': 'Milan',
  'Roma': 'Rome',
  'Torino': 'Turin',
  'Firenze': 'Florence',
  'Napoli': 'Naples',
  'Venezia': 'Venice',
  'Genova': 'Genoa',
  'Padova': 'Padua',
  'Mantova': 'Mantua',
  'Siracusa': 'Syracuse',
};

function englishCityName(city: string): string {
  return ITALIAN_TO_ENGLISH_CITY[city] || city;
}

function toTitleCase(str: string): string {
  return str.replace(/\b\w/g, (c) => c.toUpperCase());
}

function getHqOffice(fund: FundSlim) {
  return fund.offices?.find((office) => office.is_hq);
}

function getHqLabel(fund: FundSlim): string {
  const hqOffice = getHqOffice(fund);
  if (hqOffice) {
    const city = hqOffice.city?.trim() || '-';
    return city === '-' ? city : englishCityName(city);
  }
  const city = fund.hq_city?.trim() || '-';
  return city === '-' ? city : englishCityName(city);
}

const SECTOR_CELL_GAP_PX = 4;
const SECTOR_TAG_STYLE: React.CSSProperties = {
  padding: '2px 8px',
  borderRadius: '4px',
  fontSize: '13px',
  whiteSpace: 'nowrap',
};
const SECTOR_PLUS_STYLE: React.CSSProperties = {
  color: '#999',
  fontSize: '13px',
  whiteSpace: 'nowrap',
  flex: '0 0 auto',
};

function SectorGroupsCell({ sectorTags, maxVisibleGroups }: { sectorTags: string[]; maxVisibleGroups: number }) {
  const groups = useMemo(() => fundSectorGroups(sectorTags), [sectorTags]);

  if (groups.length === 0) return <span style={{ color: '#999' }}>-</span>;

  // Deterministic rendering avoids load-time flicker.
  // Keep a responsive number of visible groups and expose +N for additional groups.
  const visibleGroups = groups.slice(0, maxVisibleGroups);
  const hiddenCount = groups.length - visibleGroups.length;

  return (
    <div
      className="sector-cell"
      style={{
        display: 'flex',
        flexWrap: 'nowrap',
        gap: `${SECTOR_CELL_GAP_PX}px`,
        alignItems: 'center',
      }}
    >
      {visibleGroups.map((groupName) => {
        const color = getSectorGroupColor(groupName);
        return (
          <span
            key={groupName}
            className="sector-tag"
            style={{
              ...SECTOR_TAG_STYLE,
              background: color.bg,
              color: color.text,
            }}
            title={groupName}
          >
            {groupName}
          </span>
        );
      })}
      {hiddenCount > 0 && <span style={SECTOR_PLUS_STYLE}>+{hiddenCount}</span>}
    </div>
  );
}

export function FundsTable({ funds, portfolioCompanyNames = {}, onFilteredFundsChange }: FundsTableProps) {
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<FundCategory | 'all'>('all');
  const [sectorGroupFilter, setSectorGroupFilter] = useState<string | 'all'>('all');
  const [hqCountryFilter, setHqCountryFilter] = useState<string | 'all'>('all');
  const [invMinFilter, setInvMinFilter] = useState<number>(0);
  const [invMaxFilter, setInvMaxFilter] = useState<number>(Infinity);
  const [aumMinFilter, setAumMinFilter] = useState<number>(0);
  const [aumMaxFilter, setAumMaxFilter] = useState<number>(Infinity);
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState(0);
  const [isMobile, setIsMobile] = useState(false);
  const [sortBy, setSortBy] = useState<'name' | 'category' | 'hq' | 'aum'>('aum');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const pageSize = 25;
  const maxVisibleSectorGroups = isMobile ? 1 : 2;

  const filterSource = useMemo(() => buildDynamicFundFilterSource(funds), [funds]);
  const aumRangeMax = filterSource.aumRangeMax;
  const invRangeMax = filterSource.invRangeMax;
  const aumStops = filterSource.aumStops;
  const invStops = filterSource.invStops;

  const hasActiveInvestment = invMinFilter > 0 || (Number.isFinite(invMaxFilter) && invMaxFilter < invRangeMax);
  const activeFilterCount = [
    categoryFilter !== 'all',
    sectorGroupFilter !== 'all',
    hqCountryFilter !== 'all',
    hasActiveInvestment,
    aumMinFilter > 0 || aumMaxFilter < aumRangeMax,
  ].filter(Boolean).length;
  const hasActiveFilters = activeFilterCount > 0;

  const { primaryFunds, secondaryFunds, matchReasons, matchSummary } = useMemo(() => {
    const matchesFilters = (fund: FundSlim) => {
      if (categoryFilter !== 'all' && fund.category !== categoryFilter) return false;
      if (!matchesSectorGroupFilter(fund, sectorGroupFilter)) return false;
      if (!matchesHqCountryFilter(fund, hqCountryFilter)) return false;
      if (hasActiveInvestment) {
        const fundMin = fund.investment_min_eur || 0;
        const fundMax = fund.investment_max_eur || 0;
        if (fundMax === 0) return false;
        const filterMax = Number.isFinite(invMaxFilter) ? invMaxFilter : Infinity;
        if (fundMax < invMinFilter || fundMin > filterMax) return false;
      }
      const aum = fund.aum_eur || 0;
      if (aumMinFilter > 0 && aum < aumMinFilter) return false;
      if (aumMaxFilter < aumRangeMax && aum > aumMaxFilter) return false;
      return true;
    };

    const matchesSearch = (fund: FundSlim, query: string): { matched: boolean; reason: string; detail?: string } => {
      if (!query.trim()) return { matched: true, reason: 'name' };
      const q = query.toLowerCase();
      const categoryLabel = FUND_CATEGORY_LABELS[fund.category] || '';
      const hqOffice = getHqOffice(fund);
      const hqCity = hqOffice?.city?.toLowerCase() ?? '';
      const hqCountry = hqOffice?.country?.toLowerCase() ?? '';
      const derivedHqCountry = deriveFundHqCountry(fund)?.toLowerCase() ?? '';
      const localCity = fund.hq_city?.toLowerCase() ?? '';
      const localRegion = fund.hq_region?.toLowerCase() ?? '';
      if (fund.name.toLowerCase().includes(q) || fund.slug.includes(q)) {
        return { matched: true, reason: 'name' };
      }
      if (localCity.includes(q) || localRegion.includes(q) || hqCity.includes(q) || hqCountry.includes(q) || derivedHqCountry.includes(q)) {
        return { matched: true, reason: 'location' };
      }
      for (const t of fund.strategy_tags) {
        if (t.toLowerCase().includes(q)) return { matched: true, reason: 'sector', detail: t };
      }
      for (const t of fund.sector_tags) {
        if (t.toLowerCase().includes(q)) return { matched: true, reason: 'sector', detail: t };
      }
      if (categoryLabel.toLowerCase().includes(q)) {
        return { matched: true, reason: 'category', detail: categoryLabel };
      }
      const portfolioNames = portfolioCompanyNames[fund.slug];
      if (portfolioNames) {
        const match = portfolioNames.find((name) => name.includes(q));
        if (match) return { matched: true, reason: 'portfolio', detail: match };
      }
      return { matched: false, reason: 'none' };
    };

    const searchActive = search.trim().length > 0;

    if (!searchActive) {
      return {
        primaryFunds: funds.filter(matchesFilters),
        secondaryFunds: [] as FundSlim[],
        matchReasons: new Map<string, { reason: string; detail?: string }>(),
        matchSummary: null as null | { total: number; counts: Record<string, number> },
      };
    }

    const primary: FundSlim[] = [];
    const secondary: FundSlim[] = [];
    const reasons = new Map<string, { reason: string; detail?: string }>();
    const counts: Record<string, number> = {};

    for (const fund of funds) {
      const result = matchesSearch(fund, search);
      if (!result.matched) continue;
      reasons.set(fund.slug, { reason: result.reason, detail: result.detail });
      counts[result.reason] = (counts[result.reason] || 0) + 1;
      if (matchesFilters(fund)) {
        primary.push(fund);
      } else if (hasActiveFilters) {
        secondary.push(fund);
      }
    }

    const total = primary.length + secondary.length;
    return {
      primaryFunds: primary,
      secondaryFunds: secondary,
      matchReasons: reasons,
      matchSummary: total > 0 ? { total, counts } : null,
    };
  }, [funds, categoryFilter, sectorGroupFilter, hqCountryFilter, hasActiveInvestment, invMinFilter, invMaxFilter, aumMinFilter, aumMaxFilter, aumRangeMax, search, hasActiveFilters, portfolioCompanyNames]);

  // Sort function
  const sortFunds = (fundsToSort: FundSlim[]): FundSlim[] => {
    return [...fundsToSort].sort((a, b) => {
      let comparison = 0;
      switch (sortBy) {
        case 'name':
          comparison = a.name.localeCompare(b.name);
          break;
        case 'category':
          comparison = (FUND_CATEGORY_LABELS[a.category] || '').localeCompare(FUND_CATEGORY_LABELS[b.category] || '');
          break;
        case 'hq':
          comparison = getHqLabel(a).localeCompare(getHqLabel(b));
          break;
        case 'aum':
          comparison = (a.aum_eur || 0) - (b.aum_eur || 0);
          break;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });
  };

  const toggleSort = (column: 'name' | 'category' | 'hq' | 'aum') => {
    if (sortBy === column) {
      setSortDirection(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortDirection(column === 'name' || column === 'category' || column === 'hq' ? 'asc' : 'desc');
    }
    setPage(0);
  };

  const allFilteredFunds = useMemo(() =>
    sortFunds([...primaryFunds, ...secondaryFunds]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [primaryFunds, secondaryFunds, sortBy, sortDirection]
  );

  useEffect(() => {
    onFilteredFundsChange?.(allFilteredFunds.map(f => f.slug));
  }, [allFilteredFunds, onFilteredFundsChange]);

  const totalPages = Math.ceil(allFilteredFunds.length / pageSize);
  const paginatedFunds = allFilteredFunds.slice(page * pageSize, (page + 1) * pageSize);

  const primaryEndIndex = primaryFunds.length;
  const pageStartIndex = page * pageSize;
  const separatorIndex = primaryEndIndex - pageStartIndex;

  const clearFilters = () => {
    setCategoryFilter('all');
    setSectorGroupFilter('all');
    setHqCountryFilter('all');
    setInvMinFilter(0);
    setInvMaxFilter(invRangeMax);
    setAumMinFilter(0);
    setAumMaxFilter(aumRangeMax);
    setPage(0);
  };

  useEffect(() => {
    if (!Number.isFinite(aumMaxFilter) || aumMaxFilter > aumRangeMax) {
      setAumMaxFilter(aumRangeMax);
    }
  }, [aumMaxFilter, aumRangeMax]);

  useEffect(() => {
    if (!Number.isFinite(invMaxFilter) || invMaxFilter > invRangeMax) {
      setInvMaxFilter(invRangeMax);
    }
  }, [invMaxFilter, invRangeMax]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mediaQuery = window.matchMedia('(max-width: 768px)');
    const updateIsMobile = () => setIsMobile(mediaQuery.matches);
    updateIsMobile();
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updateIsMobile);
      return () => mediaQuery.removeEventListener('change', updateIsMobile);
    }
    mediaQuery.addListener(updateIsMobile);
    return () => mediaQuery.removeListener(updateIsMobile);
  }, []);

  const formatAumLabel = (value: number): string => {
    if (value === 0) return '\u20AC0';
    if (value === Infinity || value >= aumRangeMax) return 'Max';
    return formatAum(value);
  };

  // Build category chip items
  const categoryChipItems: ChipItem[] = filterSource.categoryChipItems;

  // Build sector group dropdown options
  const sectorGroupDropdownOptions = filterSource.sectorGroupDropdownOptions;

  // Build HQ country dropdown options
  const hqCountryDropdownOptions = filterSource.hqCountryDropdownOptions;

  return (
    <>
      <FilterBar
        search={search}
        onSearchChange={(v) => { setSearch(v); setPage(0); }}
        searchPlaceholder="Search by fund name, city, sector, or asset..."
        activeFilterCount={activeFilterCount}
        onClearAll={clearFilters}
        showFilters={showFilters}
        onToggleFilters={() => setShowFilters(!showFilters)}
        filterPanel={
          <FilterPanel>
            <FilterDropdown
              label="Sector"
              value={sectorGroupFilter}
              options={sectorGroupDropdownOptions}
              allLabel="All Sectors"
              onChange={(v) => { setSectorGroupFilter(v); setPage(0); }}
            />
            <FilterDropdown
              label="HQ Country"
              value={hqCountryFilter}
              options={hqCountryDropdownOptions}
              allLabel="All HQ Countries"
              onChange={(v) => { setHqCountryFilter(v); setPage(0); }}
            />
            {invStops.length > 1 && (
              <div>
                <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500, fontSize: '14px' }}>
                  Avg. Investment
                </label>
                <DualRangeSlider
                  min={0}
                  max={invStops.length - 1}
                  step={1}
                  valueMin={findNearestStopIndex(invStops, invMinFilter)}
                  valueMax={findNearestStopIndex(invStops, Number.isFinite(invMaxFilter) ? Math.min(invMaxFilter, invRangeMax) : invRangeMax)}
                  onChange={(minIdx, maxIdx) => {
                    setInvMinFilter(invStops[minIdx]);
                    setInvMaxFilter(invStops[maxIdx]);
                    setPage(0);
                  }}
                  formatLabel={(idx) => {
                    const v = invStops[idx];
                    if (v === 0) return '\u20AC0';
                    if (v >= invRangeMax) return 'Max';
                    return formatAum(v);
                  }}
                />
              </div>
            )}
            <div>
              <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500, fontSize: '14px' }}>
                AUM
              </label>
              <DualRangeSlider
                min={0}
                max={aumStops.length - 1}
                step={1}
                valueMin={findNearestStopIndex(aumStops, aumMinFilter)}
                valueMax={findNearestStopIndex(aumStops, aumMaxFilter === Infinity ? aumRangeMax : Math.min(aumMaxFilter, aumRangeMax))}
                onChange={(minIdx, maxIdx) => {
                  setAumMinFilter(aumStops[minIdx]);
                  setAumMaxFilter(aumStops[maxIdx]);
                  setPage(0);
                }}
                formatLabel={(idx) => formatAumLabel(aumStops[idx])}
              />
            </div>
          </FilterPanel>
        }
      >
        <FilterChips
          items={categoryChipItems}
          activeValue={categoryFilter}
          onSelect={(v) => { setCategoryFilter(v as FundCategory | 'all'); setPage(0); }}
          allLabel="All"
          allCount={funds.length}
        />
      </FilterBar>

      {matchSummary && (
        <div style={{ fontSize: '13px', color: '#999', margin: '8px 0 -4px', paddingLeft: '2px' }}>
          {matchSummary.total} {matchSummary.total === 1 ? 'fund' : 'funds'} matched
          {matchSummary.counts.name ? ` · ${matchSummary.counts.name} by name` : ''}
          {matchSummary.counts.portfolio ? ` · ${matchSummary.counts.portfolio} by assets` : ''}
          {matchSummary.counts.sector ? ` · ${matchSummary.counts.sector} by sector` : ''}
          {matchSummary.counts.location ? ` · ${matchSummary.counts.location} by location` : ''}
          {matchSummary.counts.category ? ` · ${matchSummary.counts.category} by category` : ''}
        </div>
      )}

      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
        <table
          style={{
            width: '100%',
            minWidth: '100%',
            borderCollapse: 'collapse',
            tableLayout: 'auto',
          }}
        >
          <thead>
          <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
            <th
              onClick={() => toggleSort('name')}
              style={{
                padding: '12px 12px',
                borderBottom: '1px solid #eee',
                whiteSpace: 'nowrap',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              Fund {sortBy === 'name' && (sortDirection === 'asc' ? '\u2191' : '\u2193')}
            </th>
            <th
              onClick={() => toggleSort('category')}
              style={{
                padding: '12px 12px',
                borderBottom: '1px solid #eee',
                whiteSpace: 'nowrap',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              Category {sortBy === 'category' && (sortDirection === 'asc' ? '\u2191' : '\u2193')}
            </th>
            <th
              onClick={() => toggleSort('hq')}
              style={{
                padding: '12px 12px',
                borderBottom: '1px solid #eee',
                whiteSpace: 'nowrap',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              HQ {sortBy === 'hq' && (sortDirection === 'asc' ? '\u2191' : '\u2193')}
            </th>
            <th
              onClick={() => toggleSort('aum')}
              style={{
                padding: '12px 12px',
                borderBottom: '1px solid #eee',
                whiteSpace: 'nowrap',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              <span style={{ whiteSpace: 'nowrap' }}>AUM {sortBy === 'aum' && (sortDirection === 'asc' ? '\u2191' : '\u2193')}</span>
            </th>
            <th
              style={{
                padding: '12px 12px',
                borderBottom: '1px solid #eee',
                whiteSpace: 'nowrap',
                width: '1%',
              }}
            >
              Sectors
            </th>
          </tr>
          </thead>
          <tbody>
          {paginatedFunds.map((fund, index) => (
            <React.Fragment key={fund.id}>
              {index === separatorIndex && secondaryFunds.length > 0 && separatorIndex > 0 && separatorIndex < paginatedFunds.length && (
                <tr>
                  <td colSpan={5} style={{
                    padding: '12px 12px',
                    background: '#f5f5f5',
                    color: '#666',
                    fontSize: '13px',
                    borderBottom: '1px solid #eee'
                  }}>
                    Other funds matching &ldquo;{search}&rdquo;
                  </td>
                </tr>
              )}
              <tr
                style={{ cursor: 'pointer' }}
                onClick={() => (window.location.href = `/funds/${fund.slug}`)}
                onMouseOver={(e) => (e.currentTarget.style.background = '#f9f9f9')}
                onMouseOut={(e) => (e.currentTarget.style.background = 'white')}
              >
                <td style={{ padding: '12px 12px', borderBottom: '1px solid #eee' }}>
                  <a
                    href={`/funds/${fund.slug}`}
                    style={{ color: '#0066cc', textDecoration: 'none', fontWeight: 500 }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span className="mobile-hide">{fund.name}</span>
                    <span className="mobile-show">{getShortName(fund)}</span>
                  </a>
                  {(() => {
                    const r = matchReasons.get(fund.slug);
                    if (!r || r.reason === 'name') return null;
                    let label = '';
                    if (r.reason === 'portfolio' && r.detail) label = `via assets: ${toTitleCase(r.detail)}`;
                    else if (r.reason === 'sector' && r.detail) label = `via sector: ${r.detail}`;
                    else if (r.reason === 'category' && r.detail) label = `via category: ${r.detail}`;
                    else if (r.reason === 'location') label = 'via location';
                    else label = `via ${r.reason}`;
                    return <div style={{ fontSize: '11px', color: '#aaa', marginTop: '2px' }}>{label}</div>;
                  })()}
                </td>
                <td style={{ padding: '12px 12px', borderBottom: '1px solid #eee' }}>
                  <span
                    style={{
                      background: CATEGORY_COLORS[fund.category].bg,
                      color: CATEGORY_COLORS[fund.category].text,
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '13px',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <span className="mobile-hide">{FUND_CATEGORY_LABELS[fund.category]}</span>
                    <span className="mobile-show">{SHORT_CATEGORY_LABELS[FUND_CATEGORY_LABELS[fund.category]] || FUND_CATEGORY_LABELS[fund.category]}</span>
                  </span>
                </td>
                <td style={{ padding: '12px 12px', borderBottom: '1px solid #eee', color: '#666', whiteSpace: 'nowrap' }}>
                  {getHqLabel(fund)}
                </td>
                <td style={{ padding: '12px 12px', borderBottom: '1px solid #eee', color: '#666', whiteSpace: 'nowrap' }}>
                  {fund.aum_eur ? formatAum(fund.aum_eur) : '-'}
                </td>
                <td
                  style={{
                    padding: '12px 12px',
                    borderBottom: '1px solid #eee',
                    whiteSpace: 'nowrap',
                    width: '1%',
                  }}
                >
                  <SectorGroupsCell
                    sectorTags={fund.sector_tags}
                    maxVisibleGroups={maxVisibleSectorGroups}
                  />
                </td>
              </tr>
            </React.Fragment>
          ))}
          </tbody>
        </table>
        </div>
      </div>

      {allFilteredFunds.length === 0 && (
        <p style={{ textAlign: 'center', color: '#666', padding: '24px' }}>No funds match your search.</p>
      )}

      <div
        style={{
          marginTop: '16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <p style={{ fontSize: '13px', color: '#888', margin: 0 }}>
          Showing {allFilteredFunds.length > 0 ? page * pageSize + 1 : 0}–{Math.min((page + 1) * pageSize, allFilteredFunds.length)} of{' '}
          {allFilteredFunds.length} funds
          {secondaryFunds.length > 0 && ` (${primaryFunds.length} match filters)`}
        </p>
        {totalPages > 1 && (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              style={{
                padding: '6px 12px',
                border: '1px solid #ddd',
                borderRadius: '8px',
                background: page === 0 ? '#f5f5f5' : 'white',
                cursor: page === 0 ? 'not-allowed' : 'pointer',
                fontSize: '13px',
              }}
            >
              &lt;
            </button>
            <span style={{ padding: '6px 8px', color: '#666', fontSize: '13px' }}>
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              style={{
                padding: '6px 12px',
                border: '1px solid #ddd',
                borderRadius: '8px',
                background: page >= totalPages - 1 ? '#f5f5f5' : 'white',
                cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer',
                fontSize: '13px',
              }}
            >
              &gt;
            </button>
          </div>
        )}
      </div>
    </>
  );
}
