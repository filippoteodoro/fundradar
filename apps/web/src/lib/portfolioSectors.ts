const PORTFOLIO_SECTOR_ALIASES: Record<string, string> = {
  'mixed-use / sports': 'Real Estate / Mixed-use',
  // Shorten verbose PEM sector_detail (ATECO/NACE descriptions)
  'electronic and other electrical equipment and components, except computer equipment': 'Electronic Equipment',
  'measuring, analyzing and controlling instruments; photographic, medical and optical goods; watches and clocks manufacturing': 'Precision Instruments',
  'apparel and other finished products made from fabrics and similar materials': 'Apparel & Textiles',
  'fabricated metal products, except machinery and transportation equipment': 'Fabricated Metals',
  'building construction - general contractors and operative builders': 'Construction',
  'engineering, accounting, research, management and related services': 'Professional Services',
  'security and commodity brokers, dealers, exchangers and services': 'Financial Services',
  'industrial and commercial machinery and computer equipment': 'Industrial Machinery',
  'rubber and miscellaneous plastic products manufacturing': 'Rubber & Plastics',
  'hotels, rooming houses, camps and other logging places': 'Hospitality',
  'stone, clay, glass and concrete products manufacturing': 'Building Materials',
  'heavy construction other than building - contractors': 'Heavy Construction',
  'heavy construction other than bulding - contractors': 'Heavy Construction',
  'printing, publishing, media and allied industries': 'Media & Publishing',
  'services - miscellaneous amusement and recreation': 'Leisure & Recreation',
  'pharmaceutical and allied products manufacturing': 'Pharmaceuticals',
  'electromedical and electrotherapeutic apparatus': 'Medical Devices',
  'chemicals and allied products manufacturing': 'Chemicals',
  'leather and leather products manufacturing': 'Leather Goods',
  'printing, publishing and allied industries': 'Media & Publishing',
  'petroleum refining and related industries': 'Energy / Oil & Gas',
  'transportation equipment manufacturing': 'Transportation Equipment',
  'paper and allied products manufacturing': 'Paper & Packaging',
  'miscellaneous manufacturing industries': 'Manufacturing',
  'furniture and fixtures manufacturing': 'Furniture',
  'produzione industriale di macchine e di hardware': 'Industrial Machinery',
  'other professional and social services': 'Professional Services',
  'pharmaceutical and biopharmaceutical industry': 'Pharmaceuticals',
  'pharmaceutical and biopharmaceutical': 'Pharmaceuticals',
  'health care and social services': 'Healthcare',
  // Double-char corrupted variants
  'ttrraannssppoorrttaattiioonn eeqquuiippmmeenntt mmaannuuffaaccttuurriinngg': 'Transportation Equipment',
  'chemicals and allied products mmaannuuffaaccttuurriinngg': 'Chemicals',
  'ttrraannssppoorrttaattiioonn sseerrvviicceess': 'Transportation',
  'iinndduussttrriiaall pprroodduuccttss': 'Industrial Products',
  'other professional and ssoocciaal sseervicceess': 'Professional Services',
  // Portfolio-sourced long names
  'testing, inspection & certification (tic)': 'Testing & Certification',
  'artificial intelligence / visual content': 'AI / Visual Content',
  'engineering & infrastructure monitoring': 'Engineering & Monitoring',
  'digital enabler - marketing technology': 'Marketing Technology',
  'social and healthcare infrastructures': 'Healthcare Infrastructure',
  'consumer goods & fashion accessories': 'Consumer Goods / Fashion',
  'consumer goods (cycling accessories)': 'Consumer Goods / Cycling',
};

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, ' ');
}

/**
 * Normalize portfolio sector labels for display and filtering.
 * Keeps most values as-is and only rewrites known aliases.
 */
export function normalizePortfolioSector(sector: string | null | undefined): string | null {
  if (!sector) return null;
  const trimmed = sector.trim();
  if (!trimmed) return null;
  return PORTFOLIO_SECTOR_ALIASES[normalizeToken(trimmed)] || trimmed;
}
