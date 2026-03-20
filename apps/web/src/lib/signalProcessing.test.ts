import { describe, expect, it } from 'vitest';
import type { Signal } from '@fundradar/shared';
import { cleanSignalText, reclassifySignalType } from './signalProcessing';

function makeSignal(overrides: Partial<Signal>): Signal {
  return {
    id: 'test-signal',
    fund_id: '',
    signal_type: 'other',
    title: '',
    what_changed: '',
    source_url: 'https://example.com/test',
    source_name: 'Test Source',
    published_at: null,
    observed_at: '2026-02-26T00:00:00.000Z',
    created_at: '2026-02-26T00:00:00.000Z',
    ...overrides,
  };
}

describe('signalProcessing', () => {
  it('strips redundant CDP parenthetical expansion', () => {
    const cleaned = cleanSignalText(
      "Giampaolo Di Dio is stepping down as CIO of Fondo Italiano d'Investimento SGR, 55% owned by CDP Equity (Cassa Depositi and Prestiti).",
    );
    expect(cleaned).toContain('CDP Equity');
    expect(cleaned).not.toContain('Cassa Depositi and Prestiti');
  });

  it('reclassifies merger-only exit to deal', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'exit_announced',
        title: 'Crowdfundme-Smart4Tech merger on the horizon',
        what_changed: 'Crowdfundme will merge with Smart4Tech to create a larger group.',
      }),
    );
    expect(result).toBe('deal_announced');
  });

  it('demotes static TEAM profile cards from people_move to other', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'people_move',
        page_category: 'TEAM',
        title: 'Giulio Pesenti head of Strategic Business Development',
        what_changed: '',
      }),
    );
    expect(result).toBe('other');
  });

  it('demotes role-opening titles from people_move to other', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'people_move',
        page_category: 'NEWS',
        title: 'Senior Investment Associate, Clean Energy - Capital Dynamics',
        what_changed: '',
      }),
    );
    expect(result).toBe('other');
  });

  it('reclassifies deal with departure language to people_move', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'deal_announced',
        title: "Fondo Italiano d'Investimento SGR, CIO Giampaolo Di Dio leaves",
        what_changed:
          "Giampaolo Di Dio is stepping down as CIO of Fondo Italiano d'Investimento SGR, 55% owned by CDP Equity.",
      }),
    );
    expect(result).toBe('people_move');
  });

  it('demotes TEAM investor-relations profile titles', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'people_move',
        page_category: 'TEAM',
        title: "Angela Dall'Oglio investor relations",
        what_changed: '',
      }),
    );
    expect(result).toBe('other');
  });

  it('demotes TEAM managing-director bio titles', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'people_move',
        page_category: 'TEAM',
        title:
          'Michele Romualdi managing director, Head of investor relations and strategic client partnership',
        what_changed: '',
      }),
    );
    expect(result).toBe('other');
  });

  it('demotes TEAM static parent-company blurbs', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'deal_announced',
        page_category: 'TEAM',
        title: 'Clessidra Holding is the parent company of Clessidra.',
        what_changed: '',
      }),
    );
    expect(result).toBe('other');
  });

  it('demotes annual conference listings with embedded date', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'people_move',
        title: '3rd Annual LPGP Connect CFO / COO Private Markets Switzerland 3/25/2026 - Capital Dynamics',
        what_changed: '',
      }),
    );
    expect(result).toBe('website_change');
  });

  it('preserves new team member signals as people', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'people_move',
        page_category: 'TEAM',
        title: 'New team member: Claudia Vancanti',
        what_changed: 'New team member: Claudia Vancanti (banca generali)',
      }),
    );
    expect(result).toBeNull();
  });

  it('reclassifies financial plans to report', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'other',
        title: 'Autostrade per l’Italia has approved a new €29.8B financial plan',
        what_changed: '',
      }),
    );
    expect(result).toBe('report');
  });

  it('demotes sat-down-with editorial interviews from exit to other', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'exit_announced',
        title: 'Real Deals: Investors leap on fragmented Italy as buy-and-builds soar',
        what_changed: 'BC Partners’ Stefano Ferraresi sat down with Real Deals to discuss the Italian market.',
      }),
    );
    expect(result).toBe('other');
  });

  it('reclassifies portfolio company expansion headlines to portfolio_update', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'deal_announced',
        title: 'Kiloutou strengthens its foothold in Italy',
        what_changed: '',
      }),
    );
    expect(result).toBe('portfolio_update');
  });

  it('demotes indirect buyer-parenthetical fund mentions to other', () => {
    const result = reclassifySignalType(
      makeSignal({
        signal_type: 'exit_announced',
        fund_slug: 'macquarie',
        title: "Francesco Angeloro's Shi Holding is selling a portfolio of Bess projects in southern Italy to Reden Echo, a subsidiary of the French firm Reden (Macquarie AM)",
        what_changed: '',
      }),
    );
    expect(result).toBe('other');
  });
});
