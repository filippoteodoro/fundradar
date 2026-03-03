'use client';

import { useState, useMemo, useEffect } from 'react';
import { FUND_CATEGORY_LABELS, type FundCategory, type Office } from '@fundradar/shared';
import type { UnifiedSignal } from '@/lib/signals_unified';
import { toDisplayType, SIGNAL_TYPE_STYLES, SIGNAL_TYPE_IMPORTANCE, type DisplaySignalType } from '@/lib/signalProcessing';
import { deriveFundHqCountry, matchesHqCountryFilter, matchesSectorGroupFilter } from '@/lib/fundFilters';
import { buildDynamicFundFilterSource, buildSignalTypeChipItems, SIGNAL_TYPE_FILTERS } from '@/lib/filterConfig';
import { formatAum, findNearestStopIndex } from '@/lib/fundRangeFilters';
import { fundSectorGroups } from '@/lib/sectorGroups';
import { SignalCard } from '@/components/SignalCard';
import { DualRangeSlider } from '@/components/filters/DualRangeSlider';
import { FilterBar } from '@/components/filters/FilterBar';
import { FilterChips, type ChipItem } from '@/components/filters/FilterChips';
import { FilterDropdown } from '@/components/filters/FilterDropdown';
import { FilterPanel } from '@/components/filters/FilterPanel';
import { SubscribeBanner } from '@/components/SubscribeBanner';

export interface FundMeta {
  category: FundCategory;
  sector_tags: string[];
  offices?: Office[];
  hq_city?: string | null;
  hq_region?: string | null;
  aum_eur?: number | null;
  investment_min_eur?: number | null;
  investment_max_eur?: number | null;
}

interface SignalsFeedProps {
  signals: UnifiedSignal[];
  fundPriorityScores: Record<string, number>;
  fundMetaMap?: Record<string, FundMeta>;
}

/**
 * Extract monetary value from signal text in millions of euros.
 * Handles: €300M, $7 million, £1.5 billion, €2.9 B, 7 mln $, etc.
 */
function extractAmountMillions(text: string): number {
  if (!text) return 0;
  let maxAmount = 0;

  // Pattern 1: "€300 million", "$7.5 million", "€2.9 billion", "€2.9 B", "€500 M"
  const p1 = /[€$£]\s*(\d+(?:[.,]\d+)?)\s*(?:m(?:illion|ln|io)?|b(?:illion|n|rd)?)\b/gi;
  let match;
  while ((match = p1.exec(text)) !== null) {
    const num = parseFloat(match[1].replace(',', '.'));
    if (isNaN(num) || num <= 0) continue;
    const isBillion = /b(?:illion|n|rd)?/i.test(match[0]);
    maxAmount = Math.max(maxAmount, isBillion ? num * 1000 : num);
  }

  // Pattern 2: "300 million euros", "7 mln $", "1.2 mln euros"
  const p2 = /(\d+(?:[.,]\d+)?)\s+(?:m(?:illion|ln|io)|b(?:illion|n|rd))\w*\s*(?:[€$£]|eur(?:o|os)?|usd|gbp)/gi;
  while ((match = p2.exec(text)) !== null) {
    const num = parseFloat(match[1].replace(',', '.'));
    if (isNaN(num) || num <= 0) continue;
    const isBillion = /b(?:illion|n|rd)/i.test(match[0]);
    maxAmount = Math.max(maxAmount, isBillion ? num * 1000 : num);
  }

  return maxAmount;
}

// Compute composite importance score
function getImportanceScore(signal: UnifiedSignal, fundPriorityScores: Record<string, number>): number {
  const s = signal as any;
  const quality = typeof s.quality_score === 'number' ? s.quality_score : 50;
  const evidence = typeof s.evidence_score === 'number' ? s.evidence_score : 0;
  const confidence = typeof s.confidence_score === 'number' ? s.confidence_score : 0.5;
  const relatedSlugs = Array.isArray((signal as any).related_fund_slugs)
    ? (signal as any).related_fund_slugs.filter(Boolean)
    : [];
  const slugs = relatedSlugs.length > 0 ? relatedSlugs : [signal.fund_slug || ''];
  const fundScore = Math.max(...slugs.map((slug: string) => fundPriorityScores[slug] || 0), 0);

  const typePts = SIGNAL_TYPE_IMPORTANCE[signal.signal_type] || 0;

  // Italy relevance bonus: signals confirmed as Italy-relevant rank higher
  const italyBonus = s.italy_relevant === true ? 10 : 0;

  // Deal size bonus: log-scaled so €300M >> €7M but €3B isn't infinitely more than €300M
  // €1M→0, €10M→10, €100M→20, €1B→30, €10B→40
  const text = signal.what_changed || signal.title || '';
  const amountM = extractAmountMillions(text);
  const amountBonus = amountM > 0 ? Math.max(0, Math.log10(amountM)) * 10 : 0;

  // Fund score now includes AUM (log-scaled) + Italy focus + LinkedIn priority
  return quality + (evidence * 4) + typePts + fundScore + italyBonus + (confidence * 10) + amountBonus;
}

// Signals with no confirmed event date are penalised by 7 days so they don't
// jump above signals whose published_at is known.  Some sources simply don't
// expose a date in the HTML, so the penalty is soft rather than a hard tier.
const OBSERVED_ONLY_PENALTY_MS = 60 * 60 * 1000; // 1 hour — enough to rank below same-day confirmed-date signals

function getSignalTimestamp(signal: UnifiedSignal): number {
  if (signal.published_at) {
    const ts = new Date(signal.published_at).getTime();
    return Number.isNaN(ts) ? 0 : ts;
  }
  // No confirmed event date — penalise to avoid inflating rank
  const raw = signal.observed_at || signal.created_at || '';
  if (!raw) return 0;
  const ts = new Date(raw).getTime();
  return Number.isNaN(ts) ? 0 : ts - OBSERVED_ONLY_PENALTY_MS;
}

// Sort signals: primary by effective recency (newest first), secondary by importance.
function sortSignals(signals: UnifiedSignal[], fundPriorityScores: Record<string, number>): UnifiedSignal[] {
  return [...signals].sort((a, b) => {
    const timeA = getSignalTimestamp(a);
    const timeB = getSignalTimestamp(b);

    if (timeA !== timeB) {
      return timeB - timeA;
    }

    // Same effective timestamp: prefer signals with a real published_at date
    const hasPubA = !!a.published_at;
    const hasPubB = !!b.published_at;
    if (hasPubA !== hasPubB) {
      return hasPubA ? -1 : 1;
    }

    // Same timestamp/day: rank by importance (AUM + quality + Italy relevance + type).
    return getImportanceScore(b, fundPriorityScores) - getImportanceScore(a, fundPriorityScores);
  });
}

export function SignalsFeed({ signals, fundPriorityScores, fundMetaMap = {} }: SignalsFeedProps) {
  const baseSignals = useMemo(
    () => signals.filter((s) => s.signal_type !== 'website_change'),
    [signals]
  );
  const [typeFilter, setTypeFilter] = useState<DisplaySignalType | 'all'>('all');
  const [categoryFilter, setCategoryFilter] = useState<FundCategory | 'all'>('all');
  const [sectorGroupFilter, setSectorGroupFilter] = useState<string | 'all'>('all');
  const [hqCountryFilter, setHqCountryFilter] = useState<string | 'all'>('all');
  const [invMinFilter, setInvMinFilter] = useState<number>(0);
  const [invMaxFilter, setInvMaxFilter] = useState<number>(Infinity);
  const [aumMinFilter, setAumMinFilter] = useState<number>(0);
  const [aumMaxFilter, setAumMaxFilter] = useState<number>(Infinity);
  const [search, setSearch] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState(0);
  const pageSize = 20;

  // Reset page when filters change
  useEffect(() => { setPage(0); }, [typeFilter, categoryFilter, sectorGroupFilter, hqCountryFilter, invMinFilter, invMaxFilter, aumMinFilter, aumMaxFilter, search]);

  // Build fund-level filter catalogs from the funds that have signals
  const fundMetaForSignals = useMemo(() => {
    const slugs = new Set<string>();
    for (const signal of baseSignals) {
      const related = Array.isArray((signal as any).related_fund_slugs)
        ? (signal as any).related_fund_slugs.filter(Boolean)
        : [];
      if (related.length > 0) {
        for (const slug of related) slugs.add(slug);
      } else if (signal.fund_slug) {
        slugs.add(signal.fund_slug);
      }
    }
    return Array.from(slugs)
      .map(slug => fundMetaMap[slug!])
      .filter(Boolean) as FundMeta[];
  }, [baseSignals, fundMetaMap]);
  const fundFilterSource = useMemo(() => buildDynamicFundFilterSource(fundMetaForSignals), [fundMetaForSignals]);
  const aumRangeMax = fundFilterSource.aumRangeMax;
  const invRangeMax = fundFilterSource.invRangeMax;
  const aumStops = fundFilterSource.aumStops;
  const invStops = fundFilterSource.invStops;

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

  const hasFundMetadata = fundMetaForSignals.length > 0;
  const hasActiveInvestment = invMinFilter > 0 || (Number.isFinite(invMaxFilter) && invMaxFilter < invRangeMax);
  const hasActiveAum = aumMinFilter > 0 || aumMaxFilter < aumRangeMax;

  const activeFilterCount = [
    typeFilter !== 'all',
    categoryFilter !== 'all',
    sectorGroupFilter !== 'all',
    hqCountryFilter !== 'all',
    hasActiveInvestment,
    hasActiveAum,
  ].filter(Boolean).length;

  const signalsMatchingNonTypeFilters = useMemo(() => {
    return baseSignals.filter((s) => {
      // Fund-level filters
      if (hasFundMetadata && (categoryFilter !== 'all' || sectorGroupFilter !== 'all' || hqCountryFilter !== 'all' || hasActiveInvestment || hasActiveAum)) {
        const related = Array.isArray((s as any).related_fund_slugs)
          ? (s as any).related_fund_slugs.filter(Boolean)
          : [];
        const signalSlugs = related.length > 0 ? related : [s.fund_slug || ''].filter(Boolean);
        const metas = signalSlugs
          .map((slug: string) => fundMetaMap[slug])
          .filter(Boolean) as FundMeta[];
        if (metas.length === 0) return false;
        if (categoryFilter !== 'all' && !metas.some((meta) => meta.category === categoryFilter)) return false;
        if (sectorGroupFilter !== 'all' && !metas.some((meta) => matchesSectorGroupFilter(meta, sectorGroupFilter))) return false;
        if (hqCountryFilter !== 'all' && !metas.some((meta) => matchesHqCountryFilter(meta, hqCountryFilter))) return false;
        if (hasActiveInvestment) {
          const filterMax = Number.isFinite(invMaxFilter) ? invMaxFilter : Infinity;
          const investmentMatch = metas.some((meta) => {
            const fundMin = meta.investment_min_eur || 0;
            const fundMax = meta.investment_max_eur || 0;
            if (fundMax === 0) return false;
            return !(fundMax < invMinFilter || fundMin > filterMax);
          });
          if (!investmentMatch) return false;
        }
        if (aumMinFilter > 0 || aumMaxFilter < aumRangeMax) {
          const aumMatch = metas.some((meta) => {
            const aum = meta.aum_eur || 0;
            if (aumMinFilter > 0 && aum < aumMinFilter) return false;
            if (aumMaxFilter < aumRangeMax && aum > aumMaxFilter) return false;
            return true;
          });
          if (!aumMatch) return false;
        }
      }

      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return (
        (s.what_changed || '').toLowerCase().includes(q) ||
        (s.fund_name || '').toLowerCase().includes(q)
      );
    });
  }, [baseSignals, categoryFilter, sectorGroupFilter, hqCountryFilter, hasActiveInvestment, hasActiveAum, invMinFilter, invMaxFilter, aumMinFilter, aumMaxFilter, aumRangeMax, search, hasFundMetadata, fundMetaMap]);

  const typeCounts = useMemo(() => {
    const counts = new Map<DisplaySignalType, number>();
    for (const signal of signalsMatchingNonTypeFilters) {
      const displayType = toDisplayType(signal.signal_type);
      counts.set(displayType, (counts.get(displayType) ?? 0) + 1);
    }
    return counts;
  }, [signalsMatchingNonTypeFilters]);

  const typeChipItems: ChipItem[] = useMemo(() => {
    const items = buildSignalTypeChipItems(typeCounts);
    if (typeFilter !== 'all' && !items.some((item) => item.value === typeFilter)) {
      const label = SIGNAL_TYPE_FILTERS.find((item) => item.value === typeFilter)?.label || SIGNAL_TYPE_STYLES[typeFilter]?.label || typeFilter;
      items.push({ value: typeFilter, label, count: 0 });
    }
    return items.map((type) => ({
      value: type.value,
      label: type.label,
      count: type.count,
      color: SIGNAL_TYPE_STYLES[type.value] ? { bg: SIGNAL_TYPE_STYLES[type.value].bg, text: SIGNAL_TYPE_STYLES[type.value].color } : undefined,
    }));
  }, [typeCounts, typeFilter]);

  const filteredSignals = useMemo(() => {
    const typeFiltered = typeFilter === 'all'
      ? signalsMatchingNonTypeFilters
      : signalsMatchingNonTypeFilters.filter((s) => toDisplayType(s.signal_type) === typeFilter);
    return sortSignals(typeFiltered, fundPriorityScores);
  }, [signalsMatchingNonTypeFilters, typeFilter, fundPriorityScores]);

  const {
    categoryDropdownOptions,
    allCategoryOptionCount,
    sectorGroupDropdownOptions,
    allSectorOptionCount,
    hqCountryDropdownOptions,
    allHqCountryOptionCount,
  } = useMemo(() => {
    const signalMatchesSearch = (signal: UnifiedSignal): boolean => {
      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return (
        (signal.what_changed || '').toLowerCase().includes(q) ||
        (signal.fund_name || '').toLowerCase().includes(q)
      );
    };

    const signalFundSlugs = (signal: UnifiedSignal): string[] => {
      const related = Array.isArray((signal as any).related_fund_slugs)
        ? (signal as any).related_fund_slugs.filter(Boolean)
        : [];
      return related.length > 0 ? related : [signal.fund_slug || ''].filter(Boolean);
    };

    const collectFundSlugs = (ignore: 'category' | 'sector' | 'hq') => {
      const slugs = new Set<string>();
      for (const signal of baseSignals) {
        if (typeFilter !== 'all' && toDisplayType(signal.signal_type) !== typeFilter) continue;
        if (!signalMatchesSearch(signal)) continue;

        const signalSlugs = signalFundSlugs(signal);
        const metas = signalSlugs
          .map((slug) => fundMetaMap[slug])
          .filter(Boolean) as FundMeta[];
        if (hasFundMetadata && metas.length === 0) continue;

        if (hasFundMetadata && (categoryFilter !== 'all' || sectorGroupFilter !== 'all' || hqCountryFilter !== 'all' || hasActiveInvestment || hasActiveAum)) {
          if (ignore !== 'category' && categoryFilter !== 'all' && !metas.some((meta) => meta.category === categoryFilter)) continue;
          if (ignore !== 'sector' && sectorGroupFilter !== 'all' && !metas.some((meta) => matchesSectorGroupFilter(meta, sectorGroupFilter))) continue;
          if (ignore !== 'hq' && hqCountryFilter !== 'all' && !metas.some((meta) => matchesHqCountryFilter(meta, hqCountryFilter))) continue;
          if (hasActiveInvestment) {
            const filterMax = Number.isFinite(invMaxFilter) ? invMaxFilter : Infinity;
            const investmentMatch = metas.some((meta) => {
              const fundMin = meta.investment_min_eur || 0;
              const fundMax = meta.investment_max_eur || 0;
              if (fundMax === 0) return false;
              return !(fundMax < invMinFilter || fundMin > filterMax);
            });
            if (!investmentMatch) continue;
          }
          if (hasActiveAum) {
            const aumMatch = metas.some((meta) => {
              const aum = meta.aum_eur || 0;
              if (aumMinFilter > 0 && aum < aumMinFilter) return false;
              if (aumMaxFilter < aumRangeMax && aum > aumMaxFilter) return false;
              return true;
            });
            if (!aumMatch) continue;
          }
        }

        for (const slug of signalSlugs) {
          if (fundMetaMap[slug]) slugs.add(slug);
        }
      }
      return slugs;
    };

    const categorySlugs = collectFundSlugs('category');
    const categoryCounts = new Map<FundCategory, number>();
    for (const slug of categorySlugs) {
      const meta = fundMetaMap[slug];
      if (!meta) continue;
      categoryCounts.set(meta.category, (categoryCounts.get(meta.category) ?? 0) + 1);
    }
    const dynamicCategoryDropdownOptions = fundFilterSource.categories.map((cat) => ({
      value: cat,
      label: `${FUND_CATEGORY_LABELS[cat]} (${categoryCounts.get(cat) ?? 0})`,
    }));

    const sectorSlugs = collectFundSlugs('sector');
    const sectorCounts = new Map<string, number>();
    for (const slug of sectorSlugs) {
      const meta = fundMetaMap[slug];
      if (!meta) continue;
      for (const group of fundSectorGroups(meta.sector_tags)) {
        sectorCounts.set(group, (sectorCounts.get(group) ?? 0) + 1);
      }
    }
    const dynamicSectorDropdownOptions = fundFilterSource.sectorGroupDropdownOptions.map((group) => ({
      value: group.value,
      label: `${group.value} (${sectorCounts.get(group.value) ?? 0})`,
    }));

    const hqSlugs = collectFundSlugs('hq');
    const hqCounts = new Map<string, number>();
    for (const slug of hqSlugs) {
      const meta = fundMetaMap[slug];
      if (!meta) continue;
      const country = deriveFundHqCountry(meta);
      if (!country) continue;
      hqCounts.set(country, (hqCounts.get(country) ?? 0) + 1);
    }
    const dynamicHqDropdownOptions = fundFilterSource.hqCountryDropdownOptions.map((country) => ({
      value: country.value,
      label: `${country.value} (${hqCounts.get(country.value) ?? 0})`,
    }));

    return {
      categoryDropdownOptions: dynamicCategoryDropdownOptions,
      allCategoryOptionCount: categorySlugs.size,
      sectorGroupDropdownOptions: dynamicSectorDropdownOptions,
      allSectorOptionCount: sectorSlugs.size,
      hqCountryDropdownOptions: dynamicHqDropdownOptions,
      allHqCountryOptionCount: hqSlugs.size,
    };
  }, [
    baseSignals,
    typeFilter,
    categoryFilter,
    sectorGroupFilter,
    hqCountryFilter,
    hasFundMetadata,
    hasActiveInvestment,
    hasActiveAum,
    invMinFilter,
    invMaxFilter,
    aumMinFilter,
    aumMaxFilter,
    aumRangeMax,
    search,
    fundMetaMap,
    fundFilterSource.categories,
    fundFilterSource.sectorGroupDropdownOptions,
    fundFilterSource.hqCountryDropdownOptions,
  ]);

  const totalPages = Math.ceil(filteredSignals.length / pageSize);
  const paginatedSignals = filteredSignals.slice(page * pageSize, (page + 1) * pageSize);

  const clearFilters = () => {
    setTypeFilter('all');
    setCategoryFilter('all');
    setSectorGroupFilter('all');
    setHqCountryFilter('all');
    setInvMinFilter(0);
    setInvMaxFilter(invRangeMax);
    setAumMinFilter(0);
    setAumMaxFilter(aumRangeMax);
    setSearch('');
  };

  return (
    <>
      <FilterBar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder="Search by fund or signal content..."
        activeFilterCount={activeFilterCount}
        onClearAll={clearFilters}
        showFilters={showFilters}
        onToggleFilters={() => setShowFilters(!showFilters)}
        filterPanel={
          <FilterPanel>
            {hasFundMetadata && (
              <>
                <FilterDropdown
                  label="Fund Category"
                  value={categoryFilter}
                  options={categoryDropdownOptions}
                  allLabel={`All Categories (${allCategoryOptionCount})`}
                  onChange={(v) => setCategoryFilter(v as FundCategory | 'all')}
                />
                <FilterDropdown
                  label="Sector"
                  value={sectorGroupFilter}
                  options={sectorGroupDropdownOptions}
                  allLabel={`All Sectors (${allSectorOptionCount})`}
                  onChange={setSectorGroupFilter}
                />
                <FilterDropdown
                  label="HQ Country"
                  value={hqCountryFilter}
                  options={hqCountryDropdownOptions}
                  allLabel={`All HQ Countries (${allHqCountryOptionCount})`}
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
              </>
            )}
          </FilterPanel>
        }
      >
        <FilterChips
          items={typeChipItems}
          activeValue={typeFilter}
          onSelect={(v) => setTypeFilter(v as DisplaySignalType | 'all')}
          allLabel="All"
          allCount={signalsMatchingNonTypeFilters.length}
          pinToEnd={['other']}
        />
      </FilterBar>

      {/* Signals list */}
      {filteredSignals.length === 0 ? (
        <p style={{ color: '#888', fontStyle: 'italic', padding: '24px', textAlign: 'center' }}>
          No signals match the selected filters.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {paginatedSignals.map((signal, i) => (
            <div key={signal.id}>
              <SignalCard signal={signal} showFundLink />
              {i === 4 && page === 0 && <SubscribeBanner />}
            </div>
          ))}
        </div>
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
          Showing {filteredSignals.length > 0 ? page * pageSize + 1 : 0}–{Math.min((page + 1) * pageSize, filteredSignals.length)} of{' '}
          {filteredSignals.length} signals
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
