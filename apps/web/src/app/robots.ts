import { MetadataRoute } from 'next';
import { getBaseUrl } from '@/lib/baseUrl';

export default function robots(): MetadataRoute.Robots {
  const base = getBaseUrl();
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/api/'],
    },
    sitemap: `${base}/sitemap.xml`,
    host: base,
  };
}

// Note: llms.txt and llms-full.txt are served as static files from /public/
// AI crawlers discover them at /llms.txt per the llmstxt.org specification
