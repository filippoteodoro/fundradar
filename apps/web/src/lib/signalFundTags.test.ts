import { describe, expect, it } from 'vitest';
import { buildFundMentionEntries, resolveSignalFundSlugs } from './signalFundTags';

describe('signalFundTags', () => {
  it('resolves multiple funds from one signal text and keeps primary slug first', () => {
    const entries = buildFundMentionEntries([
      { slug: 'wise-equity-sgr', name: 'Wise Equity SGR' },
      { slug: 'aksia-sgr', name: 'Aksia SGR' },
      { slug: 'alternative-capital-partners-sgr', name: 'Alternative Capital Partners SGR' },
    ]);

    const slugs = resolveSignalFundSlugs(
      {
        fund_slug: 'wise-equity-sgr',
        title: 'Wise Equity and Aksia sign an agreement',
        what_changed: 'The deal also references Alternative Capital Partners SGR.',
      },
      entries,
    );

    expect(slugs).toEqual([
      'wise-equity-sgr',
      'aksia-sgr',
      'alternative-capital-partners-sgr',
    ]);
  });

  it('does not use generic shorthand fund names', () => {
    const entries = buildFundMentionEntries([
      { slug: 'capital-dynamics-sgr', name: 'Capital Dynamics SGR' },
      { slug: 'capital-for-progress-sgr', name: 'Capital For Progress SGR' },
    ]);

    const slugs = resolveSignalFundSlugs(
      {
        title: 'Capital explores new investments in Italy',
        what_changed: '',
      },
      entries,
    );

    expect(slugs).toEqual([]);
  });

  it('does not match long legal names from generic Italian first words', () => {
    const entries = buildFundMentionEntries([
      { slug: 'cdp-venture-capital', name: 'CDP Venture Capital' },
      { slug: 'sviluppo-imprese-centro-italia-sgr', name: 'Sviluppo Imprese Centro Italia SGR' },
    ]);

    const slugs = resolveSignalFundSlugs(
      {
        fund_slug: 'cdp-venture-capital',
        title: 'Sinergy Flow closes a €7M round for the energy transition',
        what_changed: 'The company is focused on battery sviluppo and industrial scale-up.',
      },
      entries,
    );

    expect(slugs).toEqual(['cdp-venture-capital']);
  });

  it('does not auto-tag prospective bidders as related funds', () => {
    const entries = buildFundMentionEntries([
      { slug: 'apax-partners', name: 'Apax Partners' },
      { slug: 'blackstone', name: 'Blackstone' },
      { slug: 'cvc', name: 'CVC' },
    ]);

    const slugs = resolveSignalFundSlugs(
      {
        fund_slug: 'apax-partners',
        title: 'Apax launches sale of Gama Life Italia insurance activities',
        what_changed:
          'Apax Partners put up for sale GamaLife. Generali, BFF Bank, CVC, Blackstone and Brookfield among interested bidders.',
      },
      entries,
    );

    expect(slugs).toEqual(['apax-partners']);
  });

  it('keeps active seller mention but drops in-the-running bidder mentions', () => {
    const entries = buildFundMentionEntries([
      { slug: 'carlyle', name: 'Carlyle' },
      { slug: 'fondo-italiano-d-investimento-sgr', name: "Fondo Italiano d'Investimento SGR" },
      { slug: 'pai-partners', name: 'PAI Partners' },
    ]);

    const slugs = resolveSignalFundSlugs(
      {
        fund_slug: 'carlyle',
        title:
          "Mecaer (Fondo Italiano d'Investimento and Stellex Capital Management), Lazard is handling the sale process. Carlyle and PAI Partners in the running. [Rumor]",
        what_changed: '',
      },
      entries,
    );

    expect(slugs[0]).toBe('carlyle');
    expect(slugs).toContain('fondo-italiano-d-investimento-sgr');
    expect(slugs).not.toContain('pai-partners');
  });
});
