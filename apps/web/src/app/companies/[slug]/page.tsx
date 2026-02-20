import type { Metadata } from 'next';
import { getAllCompanies, getCompanyBySlug, getSignalsForCompany } from '@/lib/data';
import { notFound } from 'next/navigation';
import { CompanyDetail } from './CompanyDetail';
import { getBaseUrl } from '@/lib/baseUrl';

export function generateStaticParams() {
  return getAllCompanies().map(c => ({ slug: c.slug }));
}

export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const company = getCompanyBySlug(slug);
  if (!company) return { title: 'Company Not Found', robots: { index: false } };

  const investorCount = company.investments.length;
  const sector = company.sector || '';
  const description = company.description
    || `${company.name}${sector ? ` operates in ${sector}` : ''} and has ${investorCount} PE/VC investor${investorCount !== 1 ? 's' : ''}.`;

  return {
    title: `${company.name} — Investors & PE/VC Deals`,
    description: description.slice(0, 160),
    openGraph: {
      title: `${company.name} — PE/VC Investors`,
      description: description.slice(0, 200),
      type: 'website',
      url: `${getBaseUrl()}/companies/${company.slug}`,
    },
    alternates: {
      canonical: `/companies/${company.slug}`,
    },
  };
}

export default async function CompanyPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const company = getCompanyBySlug(slug);
  if (!company) notFound();

  const signals = getSignalsForCompany(slug);

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: company.name,
    url: company.website || `${getBaseUrl()}/companies/${company.slug}`,
    ...(company.description ? { description: company.description } : {}),
    ...(company.headquarters ? { address: { '@type': 'PostalAddress', addressLocality: company.headquarters } } : {}),
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <CompanyDetail company={company} signals={signals} />
    </div>
  );
}
