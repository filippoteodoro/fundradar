import type { Metadata } from 'next';
import {
  getAllFundsSlim,
  getAllPortfolioCompanyNames,
  getAllRealAnalytics,
  getMegaFundSlugs,
  getManualLinkedinProfileFundSlugs,
} from '@/lib/data';
import { HomeContent } from './components/HomeContent';
import { getBaseUrl } from '@/lib/baseUrl';

export const metadata: Metadata = {
  title: 'Fundradar',
  description: 'Browse 169+ private equity and venture capital funds active in Italy. Filter by sector, strategy, AUM, and location.',
  alternates: { canonical: '/' },
};

export default function HomePage() {
  const funds = getAllFundsSlim();
  const portfolioCompanyNames = getAllPortfolioCompanyNames();
  const realAnalytics = getAllRealAnalytics();
  const megaFundSlugsForDummyExclusion = getMegaFundSlugs();
  const manualLinkedinProfileFundSlugs = getManualLinkedinProfileFundSlugs();

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'Fundradar',
    url: getBaseUrl(),
    description: 'Public directory of private equity and venture capital funds in Italy with source-cited signals, portfolio tracking, and deal history.',
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>Funds in Italy</h1>
        <p style={{ margin: 0, color: '#666' }}>
          Tracking PE & VC activity in Italy using publicly available data. Not a complete database.
        </p>
      </div>

      <HomeContent
        funds={funds}
        portfolioCompanyNames={portfolioCompanyNames}
        realAnalytics={realAnalytics}
        megaFundSlugsForDummyExclusion={megaFundSlugsForDummyExclusion}
        manualLinkedinProfileFundSlugs={manualLinkedinProfileFundSlugs}
      />
    </div>
  );
}
