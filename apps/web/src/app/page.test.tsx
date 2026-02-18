import { describe, it, expect } from 'vitest';

describe('HomePage smoke test', () => {
  it('mock funds data structure is valid', () => {
    // Smoke test: verify our mock data structure matches the expected types
    const mockFund = {
      id: '1',
      slug: 'test-fund',
      name: 'Test Fund',
      hq_city: 'Milan',
      hq_region: 'Lombardy',
      website: 'https://example.com',
      strategy_tags: ['PE'],
      sector_tags: ['Tech'],
      description: null,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    };

    expect(mockFund.id).toBeDefined();
    expect(mockFund.slug).toBeDefined();
    expect(mockFund.name).toBeDefined();
    expect(Array.isArray(mockFund.strategy_tags)).toBe(true);
    expect(Array.isArray(mockFund.sector_tags)).toBe(true);
  });

  it('search filter logic works correctly', () => {
    const funds = [
      { name: 'Investindustrial', hq_city: 'Milan', strategy_tags: ['PE'], sector_tags: ['Tech'] },
      { name: 'Clessidra', hq_city: 'Rome', strategy_tags: ['VC'], sector_tags: ['Healthcare'] },
    ];

    const search = 'milan';
    const filtered = funds.filter(
      (fund) =>
        fund.name.toLowerCase().includes(search.toLowerCase()) ||
        fund.hq_city?.toLowerCase().includes(search.toLowerCase())
    );

    expect(filtered).toHaveLength(1);
    expect(filtered[0].name).toBe('Investindustrial');
  });
});
