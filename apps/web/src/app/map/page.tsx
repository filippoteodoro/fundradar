import type { Metadata } from 'next';
import { getAllFunds, getAllPortfolioCompanyNames } from '@/lib/data';
import { MapView } from './MapView';

export const metadata: Metadata = {
  title: 'Fund Map',
  description: 'Interactive map of investment fund offices across Italy.',
  alternates: { canonical: '/map' },
};

export default async function MapPage() {
  const funds = await getAllFunds();
  const portfolioCompanyNames = await getAllPortfolioCompanyNames();

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>
          Fund Map
        </h1>
        <p style={{ margin: 0, color: '#666' }}>
          Geographic distribution of funds active in Italy.
        </p>
      </div>

      <MapView funds={funds} portfolioCompanyNames={portfolioCompanyNames} />
    </div>
  );
}
