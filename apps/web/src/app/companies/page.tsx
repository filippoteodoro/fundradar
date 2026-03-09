import type { Metadata } from 'next';
import { getAllCompaniesSlim } from '@/lib/data';
import { loadUnifiedSignals, countSignalsLast30Days } from '@/lib/signals_unified';
import { CompaniesTable } from './CompaniesTable';
import { SubscribeBanner } from '@/components/SubscribeBanner';
import { getBaseUrl } from '@/lib/baseUrl';

export const metadata: Metadata = {
  title: 'Funds Backed Companies — Fundradar',
  description: 'Companies backed by funds in Italy. See which funds invested in each company, sector, and deal history.',
  alternates: { canonical: '/companies' },
};

export default function CompaniesPage() {
  const companies = getAllCompaniesSlim();
  let signalsLast30Days = 0;
  try {
    const { signals } = loadUnifiedSignals();
    signalsLast30Days = countSignalsLast30Days(signals);
  } catch {
    // silently hide if signals unavailable
  }

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: 'Funds Backed Companies',
    url: `${getBaseUrl()}/companies`,
    description: 'Companies backed by funds in Italy with investor details.',
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: '4px', marginBottom: '4px' }}>
          <h1 style={{ margin: 0, fontSize: '24px' }}>Funds Backed Companies</h1>
          {signalsLast30Days > 0 && (
            <p style={{ margin: 0, fontSize: '13px', color: '#999', whiteSpace: 'nowrap' }}>
              {signalsLast30Days} signals tracked in the last 30 days
            </p>
          )}
        </div>
        <p style={{ margin: 0, color: '#666' }}>
          Click a company to see its investors. Not a complete database.
        </p>
      </div>
      <CompaniesTable companies={companies} />
      <SubscribeBanner />
    </div>
  );
}
