import { MetadataRoute } from 'next';
import { getBaseUrl } from '@/lib/baseUrl';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/api/', '/login', '/signup', '/watchlists'],
    },
    sitemap: `${getBaseUrl()}/sitemap.xml`,
  };
}
