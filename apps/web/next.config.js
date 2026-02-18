/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@fundradar/shared'],
  experimental: {
    outputFileTracingIncludes: {
      '/*': [
        '../../data/**/*.json',
        '../../data/derived/**/*.json',
        '../../data/derived/linkedin/**/*.json',
      ],
    },
  },
};

module.exports = nextConfig;
