'use client';

import React, { useState, useMemo } from 'react';
import type { PortfolioCompany } from '@/lib/data';
import { PortfolioInsights } from './PortfolioInsights';
import { PortfolioTable } from './PortfolioTable';
import { CARD_STYLE, CARD_PADDING, badgeStyle, STATUS_STYLES, SOURCE_STYLES, PORTFOLIO_STATUS_ORDER, isUnknownSource } from '@/lib/ui';
import { normalizePortfolioSector } from '@/lib/portfolioSectors';
import { isItalianCompany } from '@/lib/italianCompany';

interface PortfolioSectionProps {
  companies: PortfolioCompany[];
  compact?: boolean;
  emptyNote?: string | null;
}

function extractCity(company: { headquarters?: string | null; data_source?: string; region?: string | null }): string {
  if (company.headquarters) {
    const hq = company.headquarters.trim();
    const parts = hq.split(',').map(s => s.trim());
    if (parts.length >= 2 && /italy/i.test(parts[parts.length - 1])) {
      return parts.slice(0, -1).join(', ');
    }
    return hq;
  }
  // PEM data is exclusively Italian PE deals
  if (company.data_source === 'pem') return 'Italy';
  if (company.region) return company.region;
  return '-';
}

function getDefaultRegionFilter(companies: PortfolioCompany[]): 'all' | 'italy' {
  const italyCount = companies.filter(c => isItalianCompany(c)).length;
  // Default to Italy filter when there's a mix of Italian and non-Italian
  if (italyCount > 0 && italyCount < companies.length) return 'italy';
  return 'all';
}

type CompactSortKey = 'company' | 'sector' | 'hq' | 'status' | 'date';

function CompactPortfolioSection({ companies }: PortfolioSectionProps) {
  const [page, setPage] = useState(0);
  const [regionFilter, setRegionFilter] = useState<'all' | 'italy'>(() => getDefaultRegionFilter(companies));
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState<CompactSortKey>('status');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const pageSize = 12;

  const toggleSort = (key: CompactSortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir(key === 'date' ? 'desc' : 'asc');
    }
    setPage(0);
  };
  const sortIndicator = (key: CompactSortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '';

  const sortedCompanies = useMemo(() => {
    return [...companies].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case 'company':
          cmp = a.company_name.localeCompare(b.company_name);
          break;
        case 'sector':
          cmp = (normalizePortfolioSector(a.sector) || a.sector || '').localeCompare(normalizePortfolioSector(b.sector) || b.sector || '');
          break;
        case 'hq':
          cmp = extractCity(a).localeCompare(extractCity(b));
          break;
        case 'status': {
          const aOrder = a.status ? (PORTFOLIO_STATUS_ORDER[a.status] ?? 2) : 2;
          const bOrder = b.status ? (PORTFOLIO_STATUS_ORDER[b.status] ?? 2) : 2;
          cmp = aOrder - bOrder;
          break;
        }
        case 'date': {
          const aDate = a.investment_date || a.entry_date || '';
          const bDate = b.investment_date || b.entry_date || '';
          if (!aDate && !bDate) cmp = 0;
          else if (!aDate) cmp = 1;
          else if (!bDate) cmp = -1;
          else cmp = aDate.localeCompare(bDate);
          break;
        }
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [companies, sortKey, sortDir]);

  const italyCount = useMemo(() => sortedCompanies.filter(c => isItalianCompany(c)).length, [sortedCompanies]);
  const showGeoFilter = italyCount > 0 && italyCount < sortedCompanies.length;

  const filteredCompanies = useMemo(() => {
    if (regionFilter === 'all') return sortedCompanies;
    return sortedCompanies.filter(c => isItalianCompany(c));
  }, [sortedCompanies, regionFilter]);
  const showSourceColumn = useMemo(
    () => filteredCompanies.some((company) => !isUnknownSource(company)),
    [filteredCompanies]
  );

  const hasActiveFilter = regionFilter !== 'all';

  const totalPages = Math.ceil(filteredCompanies.length / pageSize);
  const pageIndex = Math.min(page, Math.max(0, totalPages - 1));
  const paginatedCompanies = filteredCompanies.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize);
  const hasSectorData = useMemo(
    () => sortedCompanies.some((company) => company.sector && company.sector.trim().length > 0),
    [sortedCompanies]
  );
  const hasHqData = useMemo(
    () => sortedCompanies.some((company) => company.headquarters && company.headquarters.trim().length > 0),
    [sortedCompanies]
  );
  const hasDescriptions = useMemo(
    () => sortedCompanies.some((company) => company.description && company.description.trim().length > 0),
    [sortedCompanies]
  );

  const toggleRow = (companyId: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(companyId)) next.delete(companyId);
      else next.add(companyId);
      return next;
    });
  };

  const formatDate = (company: PortfolioCompany) =>
    company.investment_date || (company.entry_date ? company.entry_date.split('T')[0] : '-');

  return (
    <>
      <h2 style={{ marginTop: '32px', marginBottom: '16px', fontSize: '18px' }}>
        Assets ({filteredCompanies.length}{hasActiveFilter ? ` of ${sortedCompanies.length}` : ''})
      </h2>

      {showGeoFilter && (
        <div style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '16px',
          alignItems: 'center',
        }}>
          <button
            onClick={() => { setRegionFilter('all'); setPage(0); }}
            style={{
              padding: '6px 14px',
              borderRadius: '20px',
              border: regionFilter === 'all' ? '1px solid #1976d2' : '1px solid #ddd',
              fontSize: '13px',
              fontWeight: 500,
              background: regionFilter === 'all' ? '#e3f2fd' : 'white',
              color: regionFilter === 'all' ? '#1976d2' : '#666',
              cursor: 'pointer',
            }}
          >
            All ({sortedCompanies.length})
          </button>
          <button
            onClick={() => { setRegionFilter(regionFilter === 'italy' ? 'all' : 'italy'); setPage(0); }}
            style={{
              padding: '6px 14px',
              borderRadius: '20px',
              border: regionFilter === 'italy' ? '1px solid #1976d2' : '1px solid #ddd',
              fontSize: '13px',
              fontWeight: 500,
              background: regionFilter === 'italy' ? '#e3f2fd' : 'white',
              color: regionFilter === 'italy' ? '#1976d2' : '#666',
              cursor: 'pointer',
            }}
          >
            Italy ({italyCount})
          </button>
        </div>
      )}

      <div
        style={{
          ...CARD_STYLE,
          padding: CARD_PADDING,
        }}
      >
        {hasSectorData && (
          <div>
            <PortfolioInsights companies={filteredCompanies} showStatus={false} />
          </div>
        )}
        <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
          <thead>
            <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
              <th onClick={() => toggleSort('company')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>Asset{sortIndicator('company')}</th>
              <th onClick={() => toggleSort('status')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>Status{sortIndicator('status')}</th>
              <th onClick={() => toggleSort('sector')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>Sector{sortIndicator('sector')}</th>
              {hasHqData && (
                <th onClick={() => toggleSort('hq')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>HQ{sortIndicator('hq')}</th>
              )}
              {showSourceColumn && (
                <th style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>Source</th>
              )}
              <th onClick={() => toggleSort('date')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>Entry Date{sortIndicator('date')}</th>
            </tr>
          </thead>
          <tbody>
            {paginatedCompanies.map((company) => {
              const desc = company.description?.trim();
              const isExpanded = expandedRows.has(company.company_id);
              const colCount = 4 + (hasHqData ? 1 : 0) + (showSourceColumn ? 1 : 0); // Company + Status + Sector + Entry Date + optional HQ/Source
              return (
                <React.Fragment key={company.company_id}>
                  <tr
                    onClick={desc ? () => toggleRow(company.company_id) : undefined}
                    style={{ cursor: desc ? 'pointer' : 'default' }}
                  >
                    <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee', fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {desc && (
                          <span style={{
                            fontSize: '10px',
                            color: '#999',
                            transition: 'transform 0.15s',
                            transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                            display: 'inline-block',
                            flexShrink: 0,
                          }}>
                            &#9654;
                          </span>
                        )}
                        {company.website ? (
                          <a
                            href={company.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            style={{ color: '#1976d2', textDecoration: 'none' }}
                          >
                            {company.company_name}
                          </a>
                        ) : (
                          company.company_name
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee' }}>
                      {company.status ? (() => {
                        const st = STATUS_STYLES[company.status] || STATUS_STYLES.unknown;
                        return <span style={badgeStyle(st)}>{st.label}</span>;
                      })() : (
                        <span style={{ color: '#999' }}>-</span>
                      )}
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee', color: '#666' }}>
                      {company.sector ? (normalizePortfolioSector(company.sector) || company.sector) : '-'}
                    </td>
                    {hasHqData && (
                      <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee', color: '#666', fontSize: '13px' }}>
                        {extractCity(company)}
                      </td>
                    )}
                    {showSourceColumn && (
                      <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee' }}>
                        {(() => {
                          if (isUnknownSource(company)) return <span style={{ color: '#999' }}>-</span>;
                          const srcKey = company.data_source === 'pem' ? 'pem'
                            : company.data_source === 'news' ? 'news'
                            : 'website';
                          const src = SOURCE_STYLES[srcKey];
                          const label = company.source_label || src.label;
                          const style = { ...badgeStyle(src), textDecoration: 'none' as const, display: 'inline-block' as const };
                          return company.source_url ? (
                            <a href={company.source_url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} style={style}>
                              {label}
                            </a>
                          ) : (
                            <span style={badgeStyle(src)}>{label}</span>
                          );
                        })()}
                      </td>
                    )}
                    <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee', color: '#666' }}>
                      {formatDate(company)}
                    </td>
                  </tr>
                  {isExpanded && desc && (
                    <tr>
                      <td
                        colSpan={colCount}
                        style={{
                          padding: '4px 12px 12px 30px',
                          borderBottom: '1px solid #eee',
                          fontSize: '13px',
                          color: '#555',
                          lineHeight: 1.5,
                          background: '#fafafa',
                        }}
                      >
                        {desc.length > 500 ? desc.slice(0, 500) + '...' : desc}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
        </div>
      </div>

      <div
        style={{
          marginTop: '16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <p style={{ fontSize: '13px', color: '#888', margin: 0 }}>
          Showing {filteredCompanies.length > 0 ? pageIndex * pageSize + 1 : 0}–{Math.min((pageIndex + 1) * pageSize, filteredCompanies.length)} of {filteredCompanies.length} assets
        </p>
        {totalPages > 1 && (
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
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
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
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

function FullPortfolioSection({ companies }: PortfolioSectionProps) {
  const [sectorFilter, setSectorFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [websiteFilter, setWebsiteFilter] = useState<string>('all');
  const [regionFilter, setRegionFilter] = useState<'all' | 'italy'>(() => getDefaultRegionFilter(companies));

  // Get unique normalized sectors
  const sectors = useMemo(() => {
    const sectorSet = new Set<string>();
    companies.forEach(c => {
      const normalized = normalizePortfolioSector(c.sector);
      if (normalized) sectorSet.add(normalized);
    });
    return Array.from(sectorSet).sort();
  }, [companies]);

  // Get unique statuses
  const statuses = useMemo(() => {
    const statusSet = new Set<string>();
    companies.forEach(c => {
      if (c.status) statusSet.add(c.status);
    });
    return Array.from(statusSet).sort();
  }, [companies]);

  const italyCount = useMemo(() => companies.filter(c => isItalianCompany(c)).length, [companies]);
  const showGeoFilter = italyCount > 0 && italyCount < companies.length;

  // Filter and sort companies (current first, then partial, then unknown, then exited)
  const filteredCompanies = useMemo(() => {
    return companies.filter(c => {
      // Sector filter
      if (sectorFilter !== 'all') {
        const normalized = normalizePortfolioSector(c.sector);
        if (normalized !== sectorFilter) return false;
      }

      // Status filter
      if (statusFilter !== 'all') {
        if (statusFilter === 'unknown') {
          if (c.status !== null) return false;
        } else {
          if (c.status !== statusFilter) return false;
        }
      }

      // Website filter
      if (websiteFilter === 'with') {
        if (!c.website) return false;
      } else if (websiteFilter === 'without') {
        if (c.website) return false;
      }

      // Region filter
      if (regionFilter === 'italy') {
        if (!isItalianCompany(c)) return false;
      }

      return true;
    }).sort((a, b) => {
      const aOrder = a.status ? (PORTFOLIO_STATUS_ORDER[a.status] ?? 2) : 2;
      const bOrder = b.status ? (PORTFOLIO_STATUS_ORDER[b.status] ?? 2) : 2;
      if (aOrder !== bOrder) return aOrder - bOrder;
      const aDate = a.entry_date || a.investment_date || '';
      const bDate = b.entry_date || b.investment_date || '';
      if (aDate && !bDate) return -1;
      if (!aDate && bDate) return 1;
      if (aDate && bDate && aDate !== bDate) return bDate.localeCompare(aDate);
      return a.company_name.localeCompare(b.company_name);
    });
  }, [companies, sectorFilter, statusFilter, websiteFilter, regionFilter]);

  const hasActiveFilters = sectorFilter !== 'all' || statusFilter !== 'all' || websiteFilter !== 'all' || regionFilter !== 'all';

  return (
    <>
      <h2 style={{ marginTop: '32px', marginBottom: '16px', fontSize: '18px' }}>
        Assets ({filteredCompanies.length}{hasActiveFilters ? ` of ${companies.length}` : ''})
      </h2>

      {/* Filters */}
      <div style={{
        display: 'flex',
        gap: '16px',
        marginBottom: '20px',
        flexWrap: 'wrap',
        alignItems: 'center',
      }}>
        {/* Sector Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ fontSize: '14px', color: '#555', fontWeight: 500 }}>Sector:</label>
          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid #ddd',
              fontSize: '14px',
              background: 'white',
              cursor: 'pointer',
              minWidth: '140px',
            }}
          >
            <option value="all">All Sectors</option>
            {sectors.map(sector => (
              <option key={sector} value={sector}>{sector}</option>
            ))}
          </select>
        </div>

        {/* Region Filter - only show if mix of Italian and non-Italian */}
        {showGeoFilter && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ fontSize: '14px', color: '#555', fontWeight: 500 }}>Region:</label>
            <button
              onClick={() => setRegionFilter(regionFilter === 'italy' ? 'all' : 'italy')}
              style={{
                padding: '6px 14px',
                borderRadius: '20px',
                border: regionFilter === 'italy' ? '1px solid #1976d2' : '1px solid #ddd',
                fontSize: '13px',
                fontWeight: 500,
                background: regionFilter === 'italy' ? '#e3f2fd' : 'white',
                color: regionFilter === 'italy' ? '#1976d2' : '#666',
                cursor: 'pointer',
              }}
            >
              Italy ({italyCount})
            </button>
          </div>
        )}

        {/* Status Filter - only show if we have status data */}
        {statuses.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ fontSize: '14px', color: '#555', fontWeight: 500 }}>Status:</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                padding: '6px 12px',
                borderRadius: '8px',
                border: '1px solid #ddd',
                fontSize: '14px',
                background: 'white',
                cursor: 'pointer',
                minWidth: '120px',
              }}
            >
              <option value="all">All</option>
              {statuses.map(status => (
                <option key={status} value={status}>
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </option>
              ))}
              <option value="unknown">Unknown</option>
            </select>
          </div>
        )}

        {/* Website Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ fontSize: '14px', color: '#555', fontWeight: 500 }}>Website:</label>
          <select
            value={websiteFilter}
            onChange={(e) => setWebsiteFilter(e.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid #ddd',
              fontSize: '14px',
              background: 'white',
              cursor: 'pointer',
              minWidth: '120px',
            }}
          >
            <option value="all">All</option>
            <option value="with">With Website</option>
            <option value="without">Without Website</option>
          </select>
        </div>

        {/* Clear Filters */}
        {hasActiveFilters && (
          <button
            onClick={() => {
              setSectorFilter('all');
              setStatusFilter('all');
              setWebsiteFilter('all');
              setRegionFilter('all');
            }}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid #ddd',
              fontSize: '14px',
              background: '#f5f5f5',
              cursor: 'pointer',
              color: '#666',
            }}
          >
            Clear Filters
          </button>
        )}
      </div>

      {/* Charts - update based on filtered data */}
      <PortfolioInsights companies={filteredCompanies} />

      {/* Table */}
      <PortfolioTable companies={filteredCompanies} />
    </>
  );
}

export function PortfolioSection({ companies, compact = false, emptyNote }: PortfolioSectionProps) {
  if (companies.length === 0) {
    return (
      <>
        <h2 style={{ marginTop: '32px', marginBottom: '16px', fontSize: '18px' }}>
          Assets (0)
        </h2>
        {emptyNote ? (
          <div style={{
            background: '#f9f9f9',
            padding: '24px',
            borderRadius: '12px',
            border: '1px solid #eee',
          }}>
            <p style={{ margin: 0, color: '#888', fontSize: '14px', lineHeight: 1.6 }}>{emptyNote}</p>
          </div>
        ) : (
          <p style={{ color: '#888', fontStyle: 'italic' }}>No portfolio companies recorded yet.</p>
        )}
      </>
    );
  }

  return compact
    ? <CompactPortfolioSection companies={companies} compact={compact} />
    : <FullPortfolioSection companies={companies} compact={compact} />;
}
