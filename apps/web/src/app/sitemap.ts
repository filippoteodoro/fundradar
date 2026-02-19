import { MetadataRoute } from 'next';
import { getAllFunds } from '@/lib/data';
import { getBaseUrl } from '@/lib/baseUrl';

const BASE_URL = getBaseUrl();

export default function sitemap(): MetadataRoute.Sitemap {
  const funds = getAllFunds();
  const now = new Date().toISOString();

  const staticPages: MetadataRoute.Sitemap = [
    { url: BASE_URL, lastModified: now, changeFrequency: 'daily', priority: 1.0 },
    { url: `${BASE_URL}/signals`, lastModified: now, changeFrequency: 'daily', priority: 0.9 },
    { url: `${BASE_URL}/map`, lastModified: now, changeFrequency: 'weekly', priority: 0.6 },
    { url: `${BASE_URL}/about`, lastModified: now, changeFrequency: 'monthly', priority: 0.3 },
    { url: `${BASE_URL}/terms-and-conditions`, lastModified: now, changeFrequency: 'monthly', priority: 0.2 },
    { url: `${BASE_URL}/privacy-policy`, lastModified: now, changeFrequency: 'monthly', priority: 0.2 },
    { url: `${BASE_URL}/cookie-policy`, lastModified: now, changeFrequency: 'monthly', priority: 0.2 },
    { url: `${BASE_URL}/disclaimer`, lastModified: now, changeFrequency: 'monthly', priority: 0.2 },
  ];

  const fundPages: MetadataRoute.Sitemap = funds.map((fund) => ({
    url: `${BASE_URL}/funds/${fund.slug}`,
    lastModified: (fund as any).updated_at || now,
    changeFrequency: 'weekly' as const,
    priority: 0.8,
  }));

  return [...staticPages, ...fundPages];
}
