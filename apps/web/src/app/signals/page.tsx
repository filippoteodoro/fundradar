import type { Metadata } from 'next';
import { loadUnifiedSignals, countSignalsLast30Days } from '@/lib/signals_unified';
import { getAllFunds } from '@/lib/data';
import { SignalsFeed, type FundMeta } from './SignalsFeed';

export const metadata: Metadata = {
  title: 'Signals',
  description: 'Latest signals from Italian PE and VC funds: deals, exits, fundraises, hires, and news — all with source citations.',
  alternates: { canonical: '/signals' },
};

export default async function SignalsPage() {
  // Load signals from Website Monitor (PEM excluded - historical data)
  // All signals are now Italy-only (AIFI funds + manual additions)
  const { signals, fundPriorityScores } = loadUnifiedSignals();
  const signalsLast30Days = countSignalsLast30Days(signals);

  // Build fund metadata map for fund-level filters on signals
  const funds = getAllFunds();
  const fundMetaMap: Record<string, FundMeta> = {};
  for (const fund of funds) {
    fundMetaMap[fund.slug] = {
      category: fund.category,
      sector_tags: fund.sector_tags || [],
      offices: fund.offices,
      hq_city: fund.hq_city,
      hq_region: fund.hq_region,
      aum_eur: fund.aum_eur,
      investment_min_eur: fund.investment_min_eur,
      investment_max_eur: fund.investment_max_eur,
    };
  }

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: '4px', marginBottom: '4px' }}>
          <h1 style={{ margin: 0, fontSize: '24px' }}>Italy Signals Feed</h1>
          {signalsLast30Days > 0 && (
            <p style={{ margin: 0, fontSize: '13px', color: '#999', whiteSpace: 'nowrap' }}>
              {signalsLast30Days} signals tracked in the last 30 days
            </p>
          )}
        </div>
        <p style={{ margin: 0, color: '#666' }}>
          Latest publicly observed events from funds active in Italy.
        </p>
      </div>

      <SignalsFeed signals={signals} fundPriorityScores={fundPriorityScores} fundMetaMap={fundMetaMap} />
    </div>
  );
}
