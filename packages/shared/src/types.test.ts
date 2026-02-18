import { describe, it, expect } from 'vitest';
import type { Fund, Signal, SignalType } from './types.js';

describe('shared types', () => {
  it('Fund type has required fields for reliability contract', () => {
    const fund: Fund = {
      id: '1',
      slug: 'test-fund',
      name: 'Test Fund',
      category: 'pe',
      hq_city: 'Milan',
      hq_region: 'Lombardy',
      website: 'https://example.com',
      strategy_tags: ['PE'],
      sector_tags: ['Tech'],
      description: null,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    };
    expect(fund.id).toBe('1');
    expect(fund.slug).toBe('test-fund');
    expect(fund.category).toBe('pe');
  });

  it('Signal type enforces source_url and observed_at (reliability contract)', () => {
    const signal: Signal = {
      id: '1',
      fund_id: 'fund-1',
      signal_type: 'fundraise_announced',
      title: 'Fund raises €100M',
      what_changed: 'New fundraise announced',
      source_url: 'https://source.com/article',
      source_name: 'PEM',
      published_at: '2024-01-01',
      observed_at: '2024-01-02T00:00:00Z',
      created_at: '2024-01-02T00:00:00Z',
    };
    // Reliability contract: these must always be present
    expect(signal.source_url).toBeTruthy();
    expect(signal.observed_at).toBeTruthy();
    expect(signal.what_changed).toBeTruthy();
  });

  it('SignalType includes expected values', () => {
    const types: SignalType[] = [
      'fundraise_announced',
      'fundraise_closed',
      'fund_launch',
      'deal_announced',
      'exit_announced',
      'people_move',
      'job_posting',
      'website_change',
      'other',
    ];
    expect(types).toHaveLength(9);
  });
});
