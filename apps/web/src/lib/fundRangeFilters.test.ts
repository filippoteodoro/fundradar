import { describe, expect, it } from 'vitest';
import { formatAum } from './fundRangeFilters';

describe('formatAum', () => {
  it('shows no decimals and no commas for values at or above 10M/10B/10T', () => {
    expect(formatAum(10_500_000)).toBe('€10M');
    expect(formatAum(10_500_000_000)).toBe('€10B');
    expect(formatAum(10_500_000_000_000)).toBe('€10T');
    expect(formatAum(16_200_000_000)).toBe('€16B');
    expect(formatAum(10_500_000)).not.toContain(',');
    expect(formatAum(10_500_000_000)).not.toContain(',');
    expect(formatAum(10_500_000_000_000)).not.toContain(',');
  });
});
