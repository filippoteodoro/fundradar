import type { Metadata } from 'next';
import { loadUnifiedSignals } from '@/lib/signals_unified';
import { getAllFunds } from '@/lib/data';
import { SignalsFeed, type FundMeta } from './SignalsFeed';

export const metadata: Metadata = {
  title: 'Fund Signals',
  description: 'Latest signals from Italian PE and VC funds: deals, exits, fundraises, hires, and news — all with source citations.',
  alternates: { canonical: '/signals' },
};

export default async function SignalsPage() {
  // Load signals from Website Monitor (PEM excluded - historical data)
  // All signals are now Italy-only (AIFI funds + manual additions)
  const { signals, fundPriorityScores } = loadUnifiedSignals();

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
        <h1 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>
          Italy Signals Feed
        </h1>
        <p style={{ margin: 0, color: '#666' }}>
          Latest publicly observed events from PE/VC funds active in Italy.
        </p>
      </div>

      <SignalsFeed signals={signals} fundPriorityScores={fundPriorityScores} fundMetaMap={fundMetaMap} />
    </div>
  );
}
