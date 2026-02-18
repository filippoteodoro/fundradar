const PORTFOLIO_SECTOR_ALIASES: Record<string, string> = {
  'mixed-use / sports': 'Real Estate / Mixed-use',
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
