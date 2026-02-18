import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import { describe, it, expect } from 'vitest';
import {
  getManualLinkedinProfileFundSlugs,
  isManualLinkedinProfileFund,
} from './data';

interface ManualProfilesFile {
  funds?: { slug?: string }[];
}

interface FundAliasesFile {
  aliases?: Record<string, string>;
}

function getRepoRootForTest(): string {
  const candidates = [
    join(process.cwd(), '..', '..'),
    join(process.cwd(), '..'),
    process.cwd(),
  ];

  for (const candidate of candidates) {
    if (existsSync(join(candidate, 'data'))) {
      return candidate;
    }
  }

  return join(process.cwd(), '..', '..');
}

describe('LinkedIn manual profiles source of truth', () => {
  it('loads manual profile fund slugs from manual_profiles.json with alias normalization', () => {
    const repoRoot = getRepoRootForTest();
    const manualPath = join(repoRoot, 'data', 'derived', 'linkedin', 'manual_profiles.json');
    const aliasesPath = join(repoRoot, 'data', 'derived', 'fund_aliases.json');

    const manual = JSON.parse(readFileSync(manualPath, 'utf-8')) as ManualProfilesFile;
    const aliasesData = JSON.parse(readFileSync(aliasesPath, 'utf-8')) as FundAliasesFile;
    const aliases = aliasesData.aliases || {};

    const expected = Array.from(
      new Set(
        (manual.funds || [])
          .map((f) => (f.slug || '').trim())
          .filter(Boolean)
          .map((slug) => aliases[slug] || slug),
      ),
    ).sort();

    const actual = Array.from(new Set(getManualLinkedinProfileFundSlugs())).sort();
    expect(actual).toEqual(expected);
  });

  it('manual profile predicate matches the exported manual profile slug list', () => {
    const manualSlugs = getManualLinkedinProfileFundSlugs();
    for (const slug of manualSlugs) {
      expect(isManualLinkedinProfileFund(slug)).toBe(true);
    }

    expect(isManualLinkedinProfileFund('__does-not-exist__')).toBe(false);
  });
});
