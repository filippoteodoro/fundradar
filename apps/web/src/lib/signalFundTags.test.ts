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
});
