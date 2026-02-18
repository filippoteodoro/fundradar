'use client';

import { useState, useMemo, useEffect } from 'react';
import dynamic from 'next/dynamic';
import type { Fund, FundCategory } from '@fundradar/shared';
import { FUND_CATEGORY_LABELS } from '@fundradar/shared';
import { getCityCoordinates } from './cityCoordinates';
import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';
import { deriveFundHqCountry, matchesHqCountryFilter, matchesSectorGroupFilter } from '@/lib/fundFilters';
import { formatAum, findNearestStopIndex } from '@/lib/fundRangeFilters';
import { buildDynamicFundFilterSource } from '@/lib/filterConfig';
import { DualRangeSlider } from '@/components/filters/DualRangeSlider';
import { FilterBar } from '@/components/filters/FilterBar';
import { FilterChips, type ChipItem } from '@/components/filters/FilterChips';
import { FilterDropdown } from '@/components/filters/FilterDropdown';
import { FilterPanel } from '@/components/filters/FilterPanel';

const LeafletMap = dynamic(() => import('./LeafletMap').then(m => m.LeafletMap), {
  ssr: false,
  loading: () => (
    <div style={{
      height: '600px',
      background: '#e8e8e8',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: '8px',
      color: '#666',
    }}>
      Loading map...
    </div>
  ),
});

const MAP_CATEGORY_COLORS: Record<FundCategory, string> = {
  pe: '#1565c0',
  vc: '#2e7d32',
  growth: '#e65100',
  infra: '#c2185b',
  debt: '#7b1fa2',
  real_estate: '#00695c',
  holdings: '#ff6f00',
  fund_of_funds: '#512da8',
  multi_strategy: '#0277bd',
  sovereign: '#c62828',
  bank: '#37474f',
  asset_manager: '#558b2f',
  unknown: '#616161',
};

export interface MapFund {
  slug: string;
  name: string;
  category: FundCategory;
  hq_city: string | null;
  lat: number;
  lng: number;
  source: 'geocoded' | 'city';
  officeSummary?: string | null;
  officeAddress?: string | null;
}

export interface CityCluster {
  city: string;
  lat: number;
  lng: number;
  funds: Array<{ slug: string; name: string; category: FundCategory; address?: string | null }>;
}

interface MapViewProps {
  funds: Fund[];
  portfolioCompanyNames?: Record<string, string[]>;
}

export function MapView({ funds, portfolioCompanyNames = {} }: MapViewProps) {
  const [categoryFilter, setCategoryFilter] = useState<FundCategory | 'all'>('all');
  const [search, setSearch] = useState('');
  const [sectorGroupFilter, setSectorGroupFilter] = useState<string | 'all'>('all');
  const [hqCountryFilter, setHqCountryFilter] = useState<string | 'all'>('all');
  const [invMinFilter, setInvMinFilter] = useState<number>(0);
  const [invMaxFilter, setInvMaxFilter] = useState<number>(Infinity);
  const [aumMinFilter, setAumMinFilter] = useState<number>(0);
  const [aumMaxFilter, setAumMaxFilter] = useState<number>(Infinity);
  const [showFilters, setShowFilters] = useState(false);

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
    search.trim().length > 0,
  ].filter(Boolean).length;

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

  const clearFilters = () => {
    setCategoryFilter('all');
    setSectorGroupFilter('all');
    setHqCountryFilter('all');
    setInvMinFilter(0);
    setInvMaxFilter(invRangeMax);
    setAumMinFilter(0);
    setAumMaxFilter(aumRangeMax);
    setSearch('');
  };

  // Process funds into map-ready data
  const { mapFunds, cityClusters, stats } = useMemo(() => {
    const individual: MapFund[] = [];
    const cityGroups = new Map<string, CityCluster>();
    let withCoords = 0;
    let withCityFallback = 0;
    let noLocation = 0;

    for (const fund of funds) {
      // Apply all filters
      if (categoryFilter !== 'all' && fund.category !== categoryFilter) continue;
      if (!matchesSectorGroupFilter(fund, sectorGroupFilter)) continue;
      if (!matchesHqCountryFilter(fund, hqCountryFilter)) continue;
      if (hasActiveInvestment) {
        const fundMin = fund.investment_min_eur || 0;
        const fundMax = fund.investment_max_eur || 0;
        if (fundMax === 0) continue;
        const filterMax = Number.isFinite(invMaxFilter) ? invMaxFilter : Infinity;
        if (fundMax < invMinFilter || fundMin > filterMax) continue;
      }
      const aum = fund.aum_eur || 0;
      if (aumMinFilter > 0 && aum < aumMinFilter) continue;
      if (aumMaxFilter < aumRangeMax && aum > aumMaxFilter) continue;
      if (search.trim()) {
        const q = search.toLowerCase();
        const derivedHqCountry = deriveFundHqCountry(fund)?.toLowerCase() || '';
        const match =
          fund.name.toLowerCase().includes(q) ||
          fund.slug.includes(q) ||
          fund.hq_city?.toLowerCase().includes(q) ||
          fund.hq_region?.toLowerCase().includes(q) ||
          derivedHqCountry.includes(q) ||
          fund.strategy_tags?.some(t => t.toLowerCase().includes(q)) ||
          fund.sector_tags?.some(t => t.toLowerCase().includes(q)) ||
          (FUND_CATEGORY_LABELS[fund.category] || '').toLowerCase().includes(q) ||
          portfolioCompanyNames[fund.slug]?.some(name => name.toLowerCase().includes(q));
        if (!match) continue;
      }

      // Check offices array for coordinates (prefer Italian office, then HQ)
      const offices = fund.offices;
      let officeCoords: { lat: number; lng: number; city: string; summary: string | null; address: string | null } | null = null;
      if (offices && offices.length > 0) {
        const italianOffice = offices.find(o => o.is_italy && o.lat != null && o.lng != null);
        const hqOffice = offices.find(o => o.is_hq && o.lat != null && o.lng != null);
        const anyOffice = offices.find(o => o.lat != null && o.lng != null);
        const picked = italianOffice || hqOffice || anyOffice;
        if (picked && picked.lat != null && picked.lng != null) {
          const hq = offices.find(o => o.is_hq);
          const summary = picked !== hq && hq
            ? `${picked.city} office (HQ: ${hq.city})`
            : picked.city;
          const addressParts = [picked.address, picked.postal_code ? `${picked.postal_code} ${picked.city}` : picked.city, picked.country].filter(Boolean);
          officeCoords = { lat: picked.lat, lng: picked.lng, city: picked.city, summary, address: addressParts.join(', ') };
        }
      }

      if (officeCoords) {
        individual.push({
          slug: fund.slug,
          name: fund.name,
          category: fund.category,
          hq_city: officeCoords.city,
          lat: officeCoords.lat,
          lng: officeCoords.lng,
          source: 'geocoded',
          officeSummary: officeCoords.summary,
          officeAddress: officeCoords.address,
        });
        withCoords++;
      } else if (fund.hq_lat != null && fund.hq_lng != null) {
        const hqAddr = fund.hq_address
          ? [fund.hq_address, fund.hq_city].filter(Boolean).join(', ')
          : null;
        individual.push({
          slug: fund.slug,
          name: fund.name,
          category: fund.category,
          hq_city: fund.hq_city,
          lat: fund.hq_lat,
          lng: fund.hq_lng,
          source: 'geocoded',
          officeAddress: hqAddr,
        });
        withCoords++;
      } else if (fund.hq_city) {
        const cityCoord = getCityCoordinates(fund.hq_city);
        if (cityCoord) {
          const cityKey = fund.hq_city.toLowerCase().trim();
          const existing = cityGroups.get(cityKey);
          if (existing) {
            existing.funds.push({ slug: fund.slug, name: fund.name, category: fund.category, address: fund.hq_address || null });
          } else {
            cityGroups.set(cityKey, {
              city: fund.hq_city,
              lat: cityCoord.lat,
              lng: cityCoord.lng,
              funds: [{ slug: fund.slug, name: fund.name, category: fund.category, address: fund.hq_address || null }],
            });
          }
          withCityFallback++;
        } else {
          noLocation++;
        }
      } else {
        noLocation++;
      }
    }

    return {
      mapFunds: individual,
      cityClusters: Array.from(cityGroups.values()),
      stats: { withCoords, withCityFallback, noLocation, total: funds.length },
    };
  }, [funds, categoryFilter, sectorGroupFilter, hqCountryFilter, hasActiveInvestment, invMinFilter, invMaxFilter, aumMinFilter, aumMaxFilter, aumRangeMax, search, portfolioCompanyNames]);

  const showLocationSummary = stats.withCityFallback > 0 || stats.noLocation > 0;

  // Build category chip items
  const categoryChipItems: ChipItem[] = filterSource.categoryChipItems;

  // Build dropdown options
  const sectorGroupDropdownOptions = filterSource.sectorGroupDropdownOptions;

  const hqCountryDropdownOptions = filterSource.hqCountryDropdownOptions;

  return (
    <div>
      <FilterBar
        search={search}
        onSearchChange={setSearch}
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
              onChange={setSectorGroupFilter}
            />
            <FilterDropdown
              label="HQ Country"
              value={hqCountryFilter}
              options={hqCountryDropdownOptions}
              allLabel="All HQ Countries"
              onChange={setHqCountryFilter}
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
                }}
                formatLabel={(idx) => {
                  const v = aumStops[idx];
                  if (v === 0) return '\u20AC0';
                  if (v >= aumRangeMax) return 'Max';
                  return formatAum(v);
                }}
              />
            </div>
          </FilterPanel>
        }
      >
        <FilterChips
          items={categoryChipItems}
          activeValue={categoryFilter}
          onSelect={(v) => setCategoryFilter(v as FundCategory | 'all')}
          allLabel="All"
          allCount={funds.length}
        />
      </FilterBar>

      {/* Map */}
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <LeafletMap
          mapFunds={mapFunds}
          cityClusters={cityClusters}
          categoryColors={MAP_CATEGORY_COLORS}
        />
      </div>

      {/* Stats summary */}
      {showLocationSummary && (
        <div style={{
          marginTop: '16px',
          padding: '12px 16px',
          background: '#f8f9fa',
          borderRadius: '8px',
          fontSize: '13px',
          color: '#555',
          display: 'flex',
          gap: '24px',
          flexWrap: 'wrap',
        }}>
          {stats.withCityFallback > 0 && (
            <span>{stats.withCityFallback} at city level</span>
          )}
          {stats.noLocation > 0 && (
            <span style={{ color: '#999' }}>{stats.noLocation} without location data</span>
          )}
        </div>
      )}
    </div>
  );
}
