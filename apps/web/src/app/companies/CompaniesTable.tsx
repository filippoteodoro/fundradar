'use client';

import React, { useState, useMemo } from 'react';
import Link from 'next/link';
import type { CompanySlim } from '@/lib/data';
import { CARD_STYLE, CARD_PADDING, badgeStyle, STATUS_STYLES } from '@/lib/ui';
import { SECTOR_GROUPS, getSectorGroup, getSectorGroupColor } from '@/lib/sectorGroups';
import { isItalianCompany } from '@/lib/italianCompany';
import { FilterBar } from '@/components/filters/FilterBar';
import { FilterChips } from '@/components/filters/FilterChips';
import { FilterDropdown } from '@/components/filters/FilterDropdown';
import { FilterPanel } from '@/components/filters/FilterPanel';

interface CompaniesTableProps {
  companies: CompanySlim[];
}

type SortKey = 'name' | 'sector' | 'hq' | 'investors' | 'status';

function getCompanyStatus(c: CompanySlim): 'current' | 'exited' | 'unknown' {
  if (c.hasCurrentInvestment) return 'current';
  if (c.allExited) return 'exited';
  return 'unknown';
}


export function CompaniesTable({ companies }: CompaniesTableProps) {
  const [search, setSearch] = useState('');
  const [sectorGroupFilter, setSectorGroupFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'current' | 'exited'>('all');
  const [countryFilter, setCountryFilter] = useState<'italy' | 'all'>('italy');
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>('investors');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const pageSize = 50;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir(key === 'investors' ? 'desc' : 'asc');
    }
    setPage(0);
  };

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' \u2191' : ' \u2193') : '';

  // Count active filters (excluding search, which is handled by FilterBar separately)
  const activeFilterCount = [
    sectorGroupFilter !== 'all',
    statusFilter !== 'all',
    countryFilter !== 'italy',
  ].filter(Boolean).length;

  const clearFilters = () => {
    setSectorGroupFilter('all');
    setStatusFilter('all');
    setCountryFilter('italy');
    setPage(0);
  };

  const filteredCompanies = useMemo(() => {
    const searchLower = search.toLowerCase().trim();
    return companies.filter(c => {
      if (searchLower && !c.name.toLowerCase().includes(searchLower)) return false;

      if (sectorGroupFilter !== 'all') {
        const group = getSectorGroup(c.sector);
        if (group !== sectorGroupFilter) return false;
      }

      if (statusFilter !== 'all') {
        const status = getCompanyStatus(c);
        if (statusFilter === 'current' && status !== 'current') return false;
        if (statusFilter === 'exited' && status !== 'exited') return false;
      }

      if (countryFilter === 'italy') {
        if (!isItalianCompany({ headquarters: c.headquarters })) return false;
      }

      return true;
    });
  }, [companies, search, sectorGroupFilter, statusFilter, countryFilter]);

  const sortedCompanies = useMemo(() => {
    return [...filteredCompanies].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case 'name':
          cmp = a.name.localeCompare(b.name);
          break;
        case 'sector':
          cmp = (a.sector || '').localeCompare(b.sector || '');
          break;
        case 'hq':
          cmp = (a.headquarters || '').localeCompare(b.headquarters || '');
          break;
        case 'investors':
          cmp = a.investmentCount - b.investmentCount;
          break;
        case 'status': {
          const statusOrder = { current: 0, unknown: 1, exited: 2 };
          cmp = statusOrder[getCompanyStatus(a)] - statusOrder[getCompanyStatus(b)];
          break;
        }
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filteredCompanies, sortKey, sortDir]);

  const totalPages = Math.ceil(sortedCompanies.length / pageSize);
  const pageIndex = Math.min(page, Math.max(0, totalPages - 1));
  const paginatedCompanies = sortedCompanies.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize);

  // Build sector dropdown counts/options based on search + status + country filters (excluding sector filter)
  const { allSectorCount, sectorGroupOptions } = useMemo(() => {
    const searchLower = search.toLowerCase().trim();
    const baseFiltered = companies.filter(c => {
      if (searchLower && !c.name.toLowerCase().includes(searchLower)) return false;
      if (statusFilter !== 'all') {
        const status = getCompanyStatus(c);
        if (statusFilter === 'current' && status !== 'current') return false;
        if (statusFilter === 'exited' && status !== 'exited') return false;
      }
      if (countryFilter === 'italy') {
        if (!isItalianCompany({ headquarters: c.headquarters })) return false;
      }
      return true;
    });

    const counts = new Map<string, number>();
    for (const c of baseFiltered) {
      const group = getSectorGroup(c.sector);
      if (!group) continue;
      counts.set(group, (counts.get(group) ?? 0) + 1);
    }

    return {
      allSectorCount: baseFiltered.length,
      sectorGroupOptions: SECTOR_GROUPS.map((group) => ({
        value: group.name,
        label: `${group.name} (${counts.get(group.name) ?? 0})`,
      })),
    };
  }, [companies, search, statusFilter, countryFilter]);

  // Build status dropdown counts/options based on search + sector + country filters (excluding status filter)
  const { allStatusCount, statusDropdownOptions } = useMemo(() => {
    const searchLower = search.toLowerCase().trim();
    const baseFiltered = companies.filter(c => {
      if (searchLower && !c.name.toLowerCase().includes(searchLower)) return false;
      if (sectorGroupFilter !== 'all') {
        const group = getSectorGroup(c.sector);
        if (group !== sectorGroupFilter) return false;
      }
      if (countryFilter === 'italy') {
        if (!isItalianCompany({ headquarters: c.headquarters })) return false;
      }
      return true;
    });

    let currentCount = 0;
    let exitedCount = 0;
    for (const c of baseFiltered) {
      const status = getCompanyStatus(c);
      if (status === 'current') currentCount++;
      else if (status === 'exited') exitedCount++;
    }

    return {
      allStatusCount: baseFiltered.length,
      statusDropdownOptions: [
        { value: 'current', label: `Current (${currentCount})` },
        { value: 'exited', label: `Exited (${exitedCount})` },
      ],
    };
  }, [companies, search, sectorGroupFilter, countryFilter]);

  // Build country chips with counts based on currently active filters (excluding country filter).
  const { allCountryCount, countryChipItems } = useMemo(() => {
    const searchLower = search.toLowerCase().trim();
    const baseFiltered = companies.filter(c => {
      if (searchLower && !c.name.toLowerCase().includes(searchLower)) return false;
      if (sectorGroupFilter !== 'all') {
        const group = getSectorGroup(c.sector);
        if (group !== sectorGroupFilter) return false;
      }
      if (statusFilter !== 'all') {
        const status = getCompanyStatus(c);
        if (statusFilter === 'current' && status !== 'current') return false;
        if (statusFilter === 'exited' && status !== 'exited') return false;
      }
      return true;
    });

    const italyCount = baseFiltered.filter(c =>
      isItalianCompany({ headquarters: c.headquarters })
    ).length;

    return {
      allCountryCount: baseFiltered.length,
      countryChipItems: [{ value: 'italy', label: 'Italy', count: italyCount }],
    };
  }, [companies, search, sectorGroupFilter, statusFilter]);

  return (
    <>
      <FilterBar
        search={search}
        onSearchChange={(v) => { setSearch(v); setPage(0); }}
        searchPlaceholder="Search by company name..."
        activeFilterCount={activeFilterCount}
        onClearAll={clearFilters}
        showFilters={showFilters}
        onToggleFilters={() => setShowFilters(!showFilters)}
        filterPanel={
          <FilterPanel>
            <FilterDropdown
              label="Status"
              value={statusFilter}
              options={statusDropdownOptions}
              allLabel={`All (${allStatusCount})`}
              onChange={(v) => { setStatusFilter(v as typeof statusFilter); setPage(0); }}
            />
            <FilterDropdown
              label="Sector"
              value={sectorGroupFilter}
              options={sectorGroupOptions}
              allLabel={`All Sectors (${allSectorCount})`}
              onChange={(v) => { setSectorGroupFilter(v); setPage(0); }}
            />
          </FilterPanel>
        }
      >
        <FilterChips
          items={countryChipItems}
          activeValue={countryFilter}
          onSelect={(v) => { setCountryFilter(v as typeof countryFilter); setPage(0); }}
          allLabel="All"
          allCount={allCountryCount}
        />
      </FilterBar>

      {/* Table */}
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
            <thead>
              <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
                <th
                  onClick={() => toggleSort('name')}
                  aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                >
                  Company{sortIndicator('name')}
                </th>
                <th
                  onClick={() => toggleSort('sector')}
                  aria-sort={sortKey === 'sector' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                >
                  Sector{sortIndicator('sector')}
                </th>
                <th
                  onClick={() => toggleSort('hq')}
                  aria-sort={sortKey === 'hq' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                >
                  HQ{sortIndicator('hq')}
                </th>
                <th
                  onClick={() => toggleSort('investors')}
                  aria-sort={sortKey === 'investors' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                >
                  Investors{sortIndicator('investors')}
                </th>
                <th
                  onClick={() => toggleSort('status')}
                  aria-sort={sortKey === 'status' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                >
                  Status{sortIndicator('status')}
                </th>
              </tr>
            </thead>
            <tbody>
              {paginatedCompanies.map(company => {
                const status = getCompanyStatus(company);
                const sectorGroup = getSectorGroup(company.sector);
                const groupColor = sectorGroup ? getSectorGroupColor(sectorGroup) : null;

                return (
                  <tr key={company.slug}>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee', fontWeight: 500 }}>
                      <Link
                        href={`/companies/${company.slug}`}
                        style={{ color: '#1976d2', textDecoration: 'none' }}
                      >
                        {company.name}
                      </Link>
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>
                      {sectorGroup ? (
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          whiteSpace: 'nowrap',
                          background: groupColor?.bg || '#f5f5f5',
                          color: groupColor?.text || '#616161',
                        }}>
                          {sectorGroup}
                        </span>
                      ) : (
                        <span style={{ color: '#999' }}>-</span>
                      )}
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee', color: '#666', fontSize: '13px' }}>
                      {company.headquarters || '-'}
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee', textAlign: 'center' }}>
                      {company.investmentCount}
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>
                      {status === 'unknown' ? (
                        <span style={{ color: '#999' }}>-</span>
                      ) : (() => {
                        const st = STATUS_STYLES[status];
                        return <span style={badgeStyle(st)}>{st.label}</span>;
                      })()}
                    </td>
                  </tr>
                );
              })}
              {paginatedCompanies.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: '#999' }}>
                    No companies match your filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ fontSize: '13px', color: '#888', margin: 0 }}>
          Showing {sortedCompanies.length > 0 ? pageIndex * pageSize + 1 : 0}–{Math.min((pageIndex + 1) * pageSize, sortedCompanies.length)} of {sortedCompanies.length}
        </p>
        {totalPages > 1 && (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={pageIndex === 0}
              style={{
                padding: '6px 12px',
                border: '1px solid #ddd',
                borderRadius: '8px',
                background: pageIndex === 0 ? '#f5f5f5' : 'white',
                cursor: pageIndex === 0 ? 'not-allowed' : 'pointer',
                fontSize: '13px',
              }}
            >
              &lt;
            </button>
            <span style={{ padding: '6px 8px', color: '#666', fontSize: '13px' }}>
              Page {pageIndex + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={pageIndex >= totalPages - 1}
              style={{
                padding: '6px 12px',
                border: '1px solid #ddd',
                borderRadius: '8px',
                background: pageIndex >= totalPages - 1 ? '#f5f5f5' : 'white',
                cursor: pageIndex >= totalPages - 1 ? 'not-allowed' : 'pointer',
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
