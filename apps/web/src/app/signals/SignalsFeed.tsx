'use client';

import { useState, useMemo, useEffect } from 'react';
import type { FundCategory, Office } from '@fundradar/shared';
import type { UnifiedSignal } from '@/lib/signals_unified';
import { toDisplayType, SIGNAL_TYPE_STYLES, SIGNAL_TYPE_IMPORTANCE, type DisplaySignalType } from '@/lib/signalProcessing';
import { matchesHqCountryFilter, matchesSectorGroupFilter } from '@/lib/fundFilters';
import { buildDynamicFundFilterSource, buildSignalTypeChipItems } from '@/lib/filterConfig';
import { formatAum, findNearestStopIndex } from '@/lib/fundRangeFilters';
import { SignalCard } from '@/components/SignalCard';
import { DualRangeSlider } from '@/components/filters/DualRangeSlider';
import { FilterBar } from '@/components/filters/FilterBar';
import { FilterChips, type ChipItem } from '@/components/filters/FilterChips';
import { FilterDropdown } from '@/components/filters/FilterDropdown';
import { FilterPanel } from '@/components/filters/FilterPanel';

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
  const fundScore = fundPriorityScores[signal.fund_slug || ''] || 0;

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
    const slugs = new Set(baseSignals.map(s => s.fund_slug).filter(Boolean));
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

  const typeCounts = useMemo(() => {
    const counts = new Map<DisplaySignalType, number>();
    baseSignals.forEach((s) => {
      const displayType = toDisplayType(s.signal_type);
      counts.set(displayType, (counts.get(displayType) ?? 0) + 1);
    });
    return counts;
  }, [baseSignals]);

  const typeChipItems: ChipItem[] = useMemo(() => {
    return buildSignalTypeChipItems(typeCounts).map((type) => ({
        value: type.value,
        label: type.label,
        count: type.count,
        color: SIGNAL_TYPE_STYLES[type.value] ? { bg: SIGNAL_TYPE_STYLES[type.value].bg, text: SIGNAL_TYPE_STYLES[type.value].color } : undefined,
      }));
  }, [typeCounts]);

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

  const filteredSignals = useMemo(() => {
    const filtered = baseSignals.filter((s) => {
      const displayType = toDisplayType(s.signal_type);
      if (typeFilter !== 'all' && displayType !== typeFilter) return false;

      // Fund-level filters
      if (hasFundMetadata && (categoryFilter !== 'all' || sectorGroupFilter !== 'all' || hqCountryFilter !== 'all' || hasActiveInvestment || hasActiveAum)) {
        const meta = fundMetaMap[s.fund_slug || ''];
        if (!meta) return false;
        if (categoryFilter !== 'all' && meta.category !== categoryFilter) return false;
        if (!matchesSectorGroupFilter(meta, sectorGroupFilter)) return false;
        if (!matchesHqCountryFilter(meta, hqCountryFilter)) return false;
        if (hasActiveInvestment) {
          const fundMin = meta.investment_min_eur || 0;
          const fundMax = meta.investment_max_eur || 0;
          if (fundMax === 0) return false;
          const filterMax = Number.isFinite(invMaxFilter) ? invMaxFilter : Infinity;
          if (fundMax < invMinFilter || fundMin > filterMax) return false;
        }
        const aum = meta.aum_eur || 0;
        if (aumMinFilter > 0 && aum < aumMinFilter) return false;
        if (aumMaxFilter < aumRangeMax && aum > aumMaxFilter) return false;
      }

      if (!search.trim()) return true;
      const q = search.trim().toLowerCase();
      return (
        (s.what_changed || '').toLowerCase().includes(q) ||
        (s.fund_name || '').toLowerCase().includes(q)
      );
    });
    return sortSignals(filtered, fundPriorityScores);
  }, [baseSignals, typeFilter, categoryFilter, sectorGroupFilter, hqCountryFilter, hasActiveInvestment, hasActiveAum, invMinFilter, invMaxFilter, aumMinFilter, aumMaxFilter, aumRangeMax, search, fundPriorityScores, hasFundMetadata, fundMetaMap]);

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
  const categoryDropdownOptions = fundFilterSource.categoryDropdownOptions;
  const sectorGroupDropdownOptions = fundFilterSource.sectorGroupDropdownOptions;
  const hqCountryDropdownOptions = fundFilterSource.hqCountryDropdownOptions;

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
                  allLabel="All Categories"
                  onChange={(v) => setCategoryFilter(v as FundCategory | 'all')}
                />
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
          allCount={baseSignals.length}
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
              {i === 4 && page === 0 && (
                <div style={{
                  marginTop: '16px',
                  padding: '20px 24px',
                  background: 'linear-gradient(135deg, #1a1a2e 0%, #2d2d5e 100%)',
                  borderRadius: '12px',
                  textAlign: 'center',
                }}>
                  <p style={{ color: 'white', fontSize: '15px', fontWeight: 600, margin: '0 0 4px 0' }}>
                    Get these signals delivered weekly
                  </p>
                  <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '13px', margin: '0 0 14px 0' }}>
                    Deals, exits, fundraises, and key hires — straight to your inbox.
                  </p>
                  <a
                    href="/subscribe"
                    style={{
                      display: 'inline-block',
                      padding: '10px 28px',
                      background: '#2563eb',
                      color: 'white',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontWeight: 600,
                      textDecoration: 'none',
                    }}
                  >
                    Subscribe
                  </a>
                </div>
              )}
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
