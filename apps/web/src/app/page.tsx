import type { Metadata } from 'next';
import {
  getAllFundsSlim,
  getAllPortfolioCompanyNames,
  getAllRealAnalytics,
  getManualLinkedinProfileFundSlugs,
} from '@/lib/data';
import { HomeContent } from './components/HomeContent';
import { getBaseUrl } from '@/lib/baseUrl';

const HOME_SHARE_DESCRIPTION = 'Browse PE/VC funds activity in italy for free';
const HOME_OG_IMAGE_URL = '/opengraph-image?ver=orig-card-20260228a';

export const metadata: Metadata = {
  title: 'Fundradar',
  description: HOME_SHARE_DESCRIPTION,
  alternates: { canonical: '/' },
  openGraph: {
    title: 'Fundradar',
    description: HOME_SHARE_DESCRIPTION,
    type: 'website',
    url: '/',
    images: [
      {
        url: HOME_OG_IMAGE_URL,
        width: 1200,
        height: 630,
        alt: 'Fundradar',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Fundradar',
    description: HOME_SHARE_DESCRIPTION,
    images: [HOME_OG_IMAGE_URL],
  },
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
          Tracking PE/VC funds activity in Italy using publicly available data. Click on a fund to see details. Not a complete database.
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
