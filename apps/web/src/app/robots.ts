import { MetadataRoute } from 'next';
import { getBaseUrl } from '@/lib/baseUrl';

export default function robots(): MetadataRoute.Robots {
  const base = getBaseUrl();
  return {
    rules: {
      userAgent: '*',
      allow: '/',
    },
    sitemap: `${base}/sitemap.xml`,
    host: base,
  };
}

// Note: llms.txt and llms-full.txt are route handlers in src/app/llms*.txt/
// AI crawlers discover them at /llms.txt per the llmstxt.org specification
