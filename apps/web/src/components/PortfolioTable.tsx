'use client';

import { useState, useMemo, Fragment } from 'react';
import type { PortfolioCompany } from '@/lib/data';
import { CARD_STYLE, CARD_PADDING, badgeStyle, STATUS_STYLES, SOURCE_STYLES } from '@/lib/ui';
import { getSectorColor } from '@/lib/colors';
import { normalizePortfolioSector } from '@/lib/portfolioSectors';

type SortKey = 'company' | 'sector' | 'hq' | 'status' | 'date';

const STATUS_ORDER: Record<string, number> = { current: 0, partial: 1, exited: 3 };

function extractCity(headquarters: string | null | undefined): string {
  if (!headquarters) return '-';
  const hq = headquarters.trim();
  const parts = hq.split(',').map(s => s.trim());
  if (parts.length >= 2 && /italy/i.test(parts[parts.length - 1])) {
    return parts.slice(0, -1).join(', ');
  }
  return hq;
}

function isUnknownSource(company: Pick<PortfolioCompany, 'source_label' | 'source_url'>): boolean {
  const normalizedLabel = company.source_label?.trim().toLowerCase() || '';
  if (normalizedLabel === 'unknown') return true;
  return !company.source_url && !normalizedLabel;
}

function sortCompanies(companies: PortfolioCompany[], sortKey: SortKey, sortDir: 'asc' | 'desc'): PortfolioCompany[] {
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
        cmp = extractCity(a.headquarters).localeCompare(extractCity(b.headquarters));
        break;
      case 'status': {
        const aOrder = a.status ? (STATUS_ORDER[a.status] ?? 2) : 2;
        const bOrder = b.status ? (STATUS_ORDER[b.status] ?? 2) : 2;
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
}

interface PortfolioTableProps {
  companies: PortfolioCompany[];
}

export function PortfolioTable({ companies }: PortfolioTableProps) {
  const [page, setPage] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('status');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const pageSize = 30;

  const sortedCompanies = useMemo(() => sortCompanies(companies, sortKey, sortDir), [companies, sortKey, sortDir]);
  const totalPages = Math.ceil(sortedCompanies.length / pageSize);
  const pageIndex = Math.min(page, Math.max(0, totalPages - 1));
  const paginatedCompanies = sortedCompanies.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir(key === 'date' ? 'desc' : 'asc');
    }
    setPage(0);
  };

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' \u2191' : ' \u2193') : '';

  // Check if any companies have enriched data
  const hasEnrichedData = companies.some(c => c.sector || c.headquarters || c.description);
  const hasHqData = companies.some(c => c.headquarters && c.headquarters.trim().length > 0);
  const showSourceColumn = companies.some((company) => !isUnknownSource(company));

  return (
    <>
      <div
        style={{
          ...CARD_STYLE,
          padding: CARD_PADDING,
        }}
      >
        <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '14px',
          }}
        >
          <thead>
            <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
              <th onClick={() => toggleSort('company')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>Company{sortIndicator('company')}</th>
              {hasEnrichedData && (
                <th onClick={() => toggleSort('sector')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>Sector{sortIndicator('sector')}</th>
              )}
              {hasHqData && (
                <th onClick={() => toggleSort('hq')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>HQ{sortIndicator('hq')}</th>
              )}
              <th onClick={() => toggleSort('status')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>Status{sortIndicator('status')}</th>
              {showSourceColumn && (
                <th style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>Source</th>
              )}
              <th onClick={() => toggleSort('date')} style={{ padding: '10px 12px', borderBottom: '1px solid #eee', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', touchAction: 'manipulation' }}>Entry Date{sortIndicator('date')}</th>
              {hasEnrichedData && (
                <th style={{ padding: '10px 12px', borderBottom: '1px solid #eee', width: '100px' }}>Details</th>
              )}
            </tr>
          </thead>
          <tbody>
            {paginatedCompanies.map((company) => {
              const isExpanded = expandedId === company.company_id;
              const hasDetails = !!company.description;

              return (
                <Fragment key={company.company_id}>
                  <tr>
                    <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee', fontWeight: 500 }}>
                      {company.website ? (
                        <a
                          href={company.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: '#1976d2', textDecoration: 'none' }}
                        >
                          {company.company_name}
                        </a>
                      ) : (
                        company.company_name
                      )}
                    </td>
                    {hasEnrichedData && (
                      <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee' }}>
                        {company.sector ? (() => {
                          const displaySector = normalizePortfolioSector(company.sector) || company.sector;
                          const sc = getSectorColor(displaySector);
                          return (
                            <span style={{ ...badgeStyle({ bg: sc.bg, color: sc.text }), whiteSpace: 'nowrap' }}>
                              {displaySector}
                            </span>
                          );
                        })() : <span style={{ color: '#999' }}>-</span>}
                      </td>
                    )}
                    {hasHqData && (
                      <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee', color: '#666', fontSize: '13px' }}>
                        {extractCity(company.headquarters)}
                      </td>
                    )}
                    <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee' }}>
                      {company.status ? (() => {
                        const st = STATUS_STYLES[company.status] || STATUS_STYLES.unknown;
                        return <span style={badgeStyle(st)}>{st.label}</span>;
                      })() : (
                        <span style={{ color: '#999' }}>-</span>
                      )}
                    </td>
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
                            <a href={company.source_url} target="_blank" rel="noopener noreferrer" style={style}>
                              {label}
                            </a>
                          ) : (
                            <span style={badgeStyle(src)}>{label}</span>
                          );
                        })()}
                      </td>
                    )}
                    <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee', color: '#666' }}>
                      {company.investment_date || (company.entry_date ? company.entry_date.split('T')[0] : '-')}
                    </td>
                    {hasEnrichedData && (
                      <td style={{ padding: '10px 12px', borderBottom: isExpanded ? 'none' : '1px solid #eee' }}>
                        {hasDetails && (
                          <button
                            onClick={() => setExpandedId(isExpanded ? null : company.company_id)}
                            style={{
                              padding: '4px 8px',
                              border: '1px solid #ddd',
                              borderRadius: '8px',
                              background: isExpanded ? '#e3f2fd' : 'white',
                              cursor: 'pointer',
                              fontSize: '12px',
                              color: '#666',
                              touchAction: 'manipulation',
                            }}
                          >
                            {isExpanded ? 'Hide' : 'Show'}
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                  {isExpanded && hasDetails && (
                    <tr>
                      <td
                        colSpan={
                          1 // Company
                          + (hasEnrichedData ? 1 : 0) // Sector
                          + (hasHqData ? 1 : 0) // HQ
                          + 1 // Status
                          + (showSourceColumn ? 1 : 0) // Source
                          + 1 // Entry Date
                          + (hasEnrichedData ? 1 : 0) // Details
                        }
                        style={{
                          padding: '12px 24px 16px',
                          borderBottom: '1px solid #eee',
                          background: '#fafafa',
                        }}
                      >
                        {company.description && (
                          <p style={{ margin: 0, fontSize: '13px', color: '#666', lineHeight: 1.5 }}>
                            {company.description.length > 500
                              ? company.description.substring(0, 500) + '...'
                              : company.description}
                          </p>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>

        </div>
        {totalPages > 1 && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: '16px',
              paddingTop: '12px',
              borderTop: '1px solid #eee',
            }}
          >
            <p style={{ color: '#888', fontSize: '13px', margin: 0 }}>
              Showing {pageIndex * pageSize + 1}-{Math.min((pageIndex + 1) * pageSize, sortedCompanies.length)} of {sortedCompanies.length} assets
            </p>
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
                  touchAction: 'manipulation',
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
                  touchAction: 'manipulation',
                }}
              >
                &gt;
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
