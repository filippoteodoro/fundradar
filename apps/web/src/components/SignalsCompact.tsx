'use client';

import { useMemo, useState } from 'react';
import type { Signal } from '@fundradar/shared';
import { SignalCard } from '@/components/SignalCard';
import { SubscribeBanner } from '@/components/SubscribeBanner';

interface SignalsCompactProps {
  signals: Signal[];
}

// 7-day penalty for signals with no confirmed event date, so they don't rank
// above signals whose published_at is known.
const OBSERVED_ONLY_PENALTY_MS = 60 * 60 * 1000; // 1 hour — enough to rank below same-day confirmed-date signals

export function SignalsCompact({ signals }: SignalsCompactProps) {
  const [page, setPage] = useState(0);
  const pageSize = 5;

  const sortedSignals = useMemo(() => {
    return [...signals].sort((a, b) => {
      const tsA = a.published_at
        ? new Date(a.published_at).getTime()
        : new Date(a.observed_at || '').getTime() - OBSERVED_ONLY_PENALTY_MS;
      const tsB = b.published_at
        ? new Date(b.published_at).getTime()
        : new Date(b.observed_at || '').getTime() - OBSERVED_ONLY_PENALTY_MS;
      if (tsA !== tsB) return tsB - tsA;
      return (a.title || '').localeCompare(b.title || '');
    });
  }, [signals]);

  if (sortedSignals.length === 0) {
    return <p style={{ color: '#888', fontStyle: 'italic' }}>No signals recorded yet.</p>;
  }

  const totalPages = Math.ceil(sortedSignals.length / pageSize);
  const pageIndex = Math.min(page, Math.max(0, totalPages - 1));
  const paginatedSignals = sortedSignals.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize);

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {paginatedSignals.map((signal, i) => (
          <div key={signal.id}>
            <SignalCard signal={signal} />
            {pageIndex === 0 && (i === 2 || (i === paginatedSignals.length - 1 && i < 2)) && (
              <SubscribeBanner />
            )}
          </div>
        ))}
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
          Showing {sortedSignals.length > 0 ? pageIndex * pageSize + 1 : 0}–{Math.min((pageIndex + 1) * pageSize, sortedSignals.length)} of {sortedSignals.length} signals
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
