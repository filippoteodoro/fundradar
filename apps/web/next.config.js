/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@fundradar/shared'],
  experimental: {
    outputFileTracingIncludes: {
      '/*': [
        '../../data/db.json',
        '../../data/derived/**/*.json',
        '../../data/derived/linkedin/**/*.json',
      ],
    },
  },
  async headers() {
    const csp = [
      "default-src 'self'",
      // Next.js App Router injects inline scripts for hydration (__NEXT_DATA__) — unsafe-inline required
      "script-src 'self' 'unsafe-inline' https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/ https://www.googletagmanager.com https://www.google-analytics.com",
      // Recharts + Leaflet DivIcon + layout.tsx dangerouslySetInnerHTML use inline styles
      "style-src 'self' 'unsafe-inline'",
      // Leaflet tiles (OpenStreetMap) + marker images (unpkg) + inline data URIs
      "img-src 'self' data: blob: https://unpkg.com https://*.tile.openstreetmap.org",
      "font-src 'self' data:",
      // reCAPTCHA v3 makes XHR calls back to Google
      "connect-src 'self' https://www.google.com/recaptcha/ https://recaptcha.google.com/recaptcha/ https://www.google-analytics.com https://analytics.google.com https://www.googletagmanager.com https://region1.google-analytics.com",
      // reCAPTCHA v3 creates an invisible iframe
      "frame-src https://www.google.com/recaptcha/ https://recaptcha.google.com/recaptcha/",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; ');

    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Content-Security-Policy', value: csp },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
