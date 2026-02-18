import type { Metadata } from 'next';
import {
  getAllFundsSlim,
  getAllPortfolioCompanyNames,
  getAllRealAnalytics,
  getManualLinkedinProfileFundSlugs,
} from '@/lib/data';
import { HomeContent } from './components/HomeContent';
import { getBaseUrl } from '@/lib/baseUrl';

export const metadata: Metadata = {
  title: 'Fundradar',
  description: 'Browse funds activity in Italy for free.',
  alternates: { canonical: '/' },
};

export default function HomePage() {
  const funds = getAllFundsSlim();
  const portfolioCompanyNames = getAllPortfolioCompanyNames();
  const realAnalytics = getAllRealAnalytics();
  const manualLinkedinProfileFundSlugs = getManualLinkedinProfileFundSlugs();

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'Fundradar',
    url: getBaseUrl(),
    description: 'Public directory of investment funds in Italy with source-cited signals, portfolio tracking, and deal history.',
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
          Tracking funds activity in Italy using publicly available data. Not a complete database.
        </p>
      </div>

      <HomeContent
        funds={funds}
        portfolioCompanyNames={portfolioCompanyNames}
        realAnalytics={realAnalytics}
        manualLinkedinProfileFundSlugs={manualLinkedinProfileFundSlugs}
      />
    </div>
  );
}
