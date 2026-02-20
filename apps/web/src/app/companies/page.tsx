import type { Metadata } from 'next';
import { getAllCompaniesSlim } from '@/lib/data';
import { CompaniesTable } from './CompaniesTable';
import { getBaseUrl } from '@/lib/baseUrl';

export const metadata: Metadata = {
  title: 'PE & VC-Backed Companies — Fundradar',
  description: 'Browse PE and VC-backed companies in Italy. See which funds invested in each company, sector, and deal history.',
  alternates: { canonical: '/companies' },
};

export default function CompaniesPage() {
  const companies = getAllCompaniesSlim();

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: 'PE & VC-Backed Companies',
    url: `${getBaseUrl()}/companies`,
    description: 'Directory of PE and VC-backed companies in Italy with investor details.',
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '24px' }}>PE & VC-Backed Companies</h1>
        <p style={{ margin: 0, color: '#666' }}>
          Companies backed by PE and VC funds. Not a complete database. Click a company to see its investors.
        </p>
      </div>
      <CompaniesTable companies={companies} />
    </div>
  );
}
