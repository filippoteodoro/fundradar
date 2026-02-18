import { describe, expect, it } from 'vitest';
import { normalizePortfolioSector } from './portfolioSectors';

describe('normalizePortfolioSector', () => {
  it('maps mixed-use sports assets to real estate mixed-use label', () => {
    expect(normalizePortfolioSector('Mixed-use / Sports')).toBe('Real Estate / Mixed-use');
  });

  it('passes through unrelated sector labels', () => {
    expect(normalizePortfolioSector('Healthcare')).toBe('Healthcare');
  });

  it('returns null for empty values', () => {
    expect(normalizePortfolioSector(null)).toBeNull();
    expect(normalizePortfolioSector('   ')).toBeNull();
  });
});
