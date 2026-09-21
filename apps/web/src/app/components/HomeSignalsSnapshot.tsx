'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import type { UnifiedSignal } from '@/lib/signals_unified';
import { SignalCard } from '@/components/SignalCard';

interface Props {
  signals: UnifiedSignal[];
  filteredSlugSet: Set<string>;
}

export function HomeSignalsSnapshot({ signals, filteredSlugSet }: Props) {
  const visibleSignals = useMemo(() => {
    return signals
      .filter(s =>
        filteredSlugSet.has(s.fund_slug ?? '') ||
        (s.related_fund_slugs ?? []).some(r => filteredSlugSet.has(r))
      )
      .slice(0, 5);
  }, [signals, filteredSlugSet]);

  if (visibleSignals.length === 0) return null;

  return (
    <div style={{ marginTop: '48px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '16px' }}>
        <h2 style={{ margin: 0, fontSize: '20px' }}>Recent Signals</h2>
        <Link href="/signals" style={{ color: '#1976d2', textDecoration: 'none', fontSize: '14px' }}>
          View all signals →
        </Link>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {visibleSignals.map(signal => (
          <SignalCard key={signal.id} signal={signal} showFundLink />
        ))}
      </div>
    </div>
  );
}
