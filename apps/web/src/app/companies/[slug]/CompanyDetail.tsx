'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import type { Company, CompanyInvestment, Signal } from '@fundradar/shared';
import { CARD_STYLE, CARD_PADDING, badgeStyle, STATUS_STYLES, SOURCE_STYLES, PORTFOLIO_STATUS_ORDER, isUnknownSource } from '@/lib/ui';
import { getSectorGroup, getSectorGroupColor } from '@/lib/sectorGroups';
import { SignalCard } from '@/components/SignalCard';

interface CompanySignal extends Signal {
  fund_name: string;
  fund_slug: string;
}

interface CompanyDetailProps {
  company: Company;
  signals?: CompanySignal[];
}


function sortInvestments(investments: CompanyInvestment[]): CompanyInvestment[] {
  return [...investments].sort((a, b) => {
    // Current before exited
    const aOrder = a.status ? (PORTFOLIO_STATUS_ORDER[a.status] ?? 2) : 2;
    const bOrder = b.status ? (PORTFOLIO_STATUS_ORDER[b.status] ?? 2) : 2;
    if (aOrder !== bOrder) return aOrder - bOrder;
    // Most recent first
    const aDate = a.entry_date || '';
    const bDate = b.entry_date || '';
    if (aDate && !bDate) return -1;
    if (!aDate && bDate) return 1;
    if (aDate && bDate) return bDate.localeCompare(aDate);
    return a.fund_name.localeCompare(b.fund_name);
  });
}

function getSourceStyleKey(dataSource: string | null): string {
  if (dataSource === 'pem') return 'pem';
  if (dataSource === 'news' || dataSource === 'signal_news' || dataSource === 'signal_news_verified') return 'news';
  return 'website';
}

const INITIAL_SIGNAL_COUNT = 5;

export function CompanyDetail({ company, signals = [] }: CompanyDetailProps) {
  const [showAllSignals, setShowAllSignals] = useState(false);
  const sectorGroup = getSectorGroup(company.sector);
  const groupColor = sectorGroup ? getSectorGroupColor(sectorGroup) : null;
  const sorted = sortInvestments(company.investments);
  const currentCount = company.investments.filter(i => i.status === 'current').length;
  const exitedCount = company.investments.filter(i => i.status === 'exited').length;
  const visibleSignals = showAllSignals ? signals : signals.slice(0, INITIAL_SIGNAL_COUNT);

  return (
    <>
      {/* Breadcrumb */}
      <div style={{ marginBottom: '16px', fontSize: '14px' }}>
        <Link href="/companies" style={{ color: '#1976d2', textDecoration: 'none' }}>
          Companies
        </Link>
        <span style={{ color: '#999', margin: '0 8px' }}>/</span>
        <span style={{ color: '#333' }}>{company.name}</span>
      </div>

      {/* Header card */}
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING, marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h1 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>{company.name}</h1>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
              {sectorGroup && (
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
              )}
              {company.sector && company.sector !== sectorGroup && (
                <span style={{ fontSize: '13px', color: '#666' }}>{company.sector}</span>
              )}
            </div>
          </div>
          {company.website && (
            <a
              href={company.website}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: '#1976d2',
                textDecoration: 'none',
                fontSize: '14px',
                whiteSpace: 'nowrap',
              }}
            >
              Website &rarr;
            </a>
          )}
        </div>

        {/* Metadata row */}
        <div style={{ display: 'flex', gap: '24px', marginTop: '12px', flexWrap: 'wrap', fontSize: '14px', color: '#555' }}>
          {company.headquarters && (
            <div>
              <span style={{ color: '#999' }}>HQ: </span>{company.headquarters}
            </div>
          )}
          <div>
            <span style={{ color: '#999' }}>Investors: </span>
            {company.investments.length}
            {currentCount > 0 && exitedCount > 0 && (
              <span style={{ color: '#999' }}> ({currentCount} current, {exitedCount} exited)</span>
            )}
          </div>
        </div>

        {/* Description */}
        {company.description && (
          <p style={{ margin: '12px 0 0 0', color: '#555', fontSize: '14px', lineHeight: 1.6 }}>
            {company.description}
          </p>
        )}
      </div>

      {/* Investors table */}
      <h2 style={{ margin: '0 0 16px 0', fontSize: '18px' }}>
        Investors ({company.investments.length})
      </h2>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
            <thead>
              <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>Fund</th>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>Status</th>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>Entry Date</th>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>Stage</th>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>Source</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((inv, i) => {
                const st = inv.status ? (STATUS_STYLES[inv.status] || STATUS_STYLES.unknown) : STATUS_STYLES.unknown;
                const srcKey = getSourceStyleKey(inv.data_source);
                const src = SOURCE_STYLES[srcKey];
                const label = inv.source_label || src.label;

                return (
                  <tr key={`${inv.fund_slug}-${i}`}>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee', fontWeight: 500 }}>
                      <Link
                        href={`/funds/${inv.fund_slug}`}
                        style={{ color: '#1976d2', textDecoration: 'none' }}
                      >
                        {inv.fund_name}
                      </Link>
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>
                      {inv.status ? (
                        <span style={badgeStyle(st)}>{st.label}</span>
                      ) : (
                        <span style={{ color: '#999' }}>-</span>
                      )}
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee', color: '#666' }}>
                      {inv.entry_date
                        ? (inv.entry_date.endsWith('-01-01') ? inv.entry_date.slice(0, 4) : inv.entry_date.split('T')[0])
                        : '-'}
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee', color: '#666' }}>
                      {inv.investment_stage || '-'}
                    </td>
                    <td style={{ padding: '10px 12px', borderBottom: '1px solid #eee' }}>
                      {(() => {
                        if (isUnknownSource(inv)) {
                          return <span style={{ color: '#999' }}>-</span>;
                        }
                        return inv.source_url ? (
                          <a
                            href={inv.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ ...badgeStyle(src), textDecoration: 'none', display: 'inline-block' }}
                          >
                            {label}
                          </a>
                        ) : (
                          <span style={badgeStyle(src)}>{label}</span>
                        );
                      })()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Signals section — only shown when there are matching signals */}
      {signals.length > 0 && (
        <>
          <h2 style={{ margin: '24px 0 16px 0', fontSize: '18px' }}>
            Signals ({signals.length})
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {visibleSignals.map((signal) => (
              <SignalCard
                key={signal.id}
                signal={signal}
                showFundLink={true}
              />
            ))}
          </div>
          {signals.length > INITIAL_SIGNAL_COUNT && (
            <button
              onClick={() => setShowAllSignals(!showAllSignals)}
              style={{
                marginTop: '12px',
                padding: '8px 16px',
                background: 'none',
                border: '1px solid #ddd',
                borderRadius: '8px',
                color: '#1976d2',
                cursor: 'pointer',
                fontSize: '14px',
              }}
            >
              {showAllSignals ? 'Show less' : `Show all ${signals.length} signals`}
            </button>
          )}
        </>
      )}
    </>
  );
}
