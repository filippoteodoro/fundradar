import type { Metadata } from 'next';
import { getAllCompaniesSlim } from '@/lib/data';
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
        <h1 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>Funds Backed Companies</h1>
        <p style={{ margin: 0, color: '#666' }}>
          Click a company to see its investors. Not a complete database.
        </p>
      </div>
      <CompaniesTable companies={companies} />
      <SubscribeBanner />
    </div>
  );
}
