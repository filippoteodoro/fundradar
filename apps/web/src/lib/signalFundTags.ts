import type { Signal } from '@fundradar/shared';

export interface FundReference {
  slug: string;
  name: string;
}

export interface FundMentionEntry {
  slug: string;
  pattern: string;
  regex: RegExp;
}

const GENERIC_SHORT_BRANDS = new Set([
  'capital',
  'partners',
  'private',
  'venture',
  'equity',
  'asset',
  'management',
  'group',
  'fondo',
  'fund',
  'team',
  // Common nouns/adjectives that appear as first words of multi-word fund names
  // but are too generic to use as standalone matching patterns
  'cherry',
  'silver',
  'golden',
  'bridge',
  'impact',
  'summit',
  'spring',
  'castle',
  'anchor',
  'global',
  'europe',
  'invest',
  'select',
  'market',
  'search',
  'towers',
  'credit',
  'hellman',
  'charterhouse',
  'tamburi',
  'searchlight',
  'stirling',
]);

function normalizePhrase(value: string): string {
  return (value || '')
    .toLowerCase()
    .replace(/['’]/g, ' ')
    .replace(/[^a-z0-9à-öø-ÿ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function toPatternRegex(pattern: string): RegExp {
  const escaped = pattern
    .split(' ')
    .filter(Boolean)
    .map(escapeRegex)
    .join('\\s+');
  return new RegExp(`(?:^|\\s)${escaped}(?=\\s|$)`, 'i');
}

function addOwner(map: Map<string, Set<string>>, phrase: string, slug: string): void {
  const normalized = normalizePhrase(phrase);
  if (!normalized || normalized.length < 4 || !slug) return;
  let owners = map.get(normalized);
  if (!owners) {
    owners = new Set<string>();
    map.set(normalized, owners);
  }
  owners.add(slug);
}

export function buildFundMentionEntries(funds: FundReference[]): FundMentionEntry[] {
  const phraseOwners = new Map<string, Set<string>>();
  const shortOwners = new Map<string, Set<string>>();

  for (const fund of funds) {
    const slug = (fund.slug || '').trim();
    const rawName = (fund.name || '').trim();
    if (!slug || !rawName) continue;

    const full = normalizePhrase(rawName);
    addOwner(phraseOwners, full, slug);

    const cleaned = full
      .replace(/\b(?:sgr|sicaf|sim|spa|srl|sa|ltd|inc)\b$/i, '')
      .trim();
    if (cleaned && cleaned !== full) {
      addOwner(phraseOwners, cleaned, slug);
    }

    // Extract first-word short brand for unambiguous fund names (e.g. "azimut"
    // from "Azimut Libera Impresa SGR"). The uniqueness filter below rejects
    // patterns shared by multiple funds — the previous ≤2-word guard was
    // redundant and blocked valid single-word matches for 3+ word fund names.
    const words = (cleaned || full).split(' ').filter(Boolean);
    const first = words[0] || '';
    if (
      first.length >= 6 &&
      !GENERIC_SHORT_BRANDS.has(first)
    ) {
      addOwner(shortOwners, first, slug);
    }
  }

  // Keep shorthand patterns only when they unambiguously map to a single fund.
  for (const [short, owners] of shortOwners.entries()) {
    if (owners.size !== 1) continue;
    for (const slug of owners) addOwner(phraseOwners, short, slug);
  }

  const entries: FundMentionEntry[] = [];
  for (const [pattern, owners] of phraseOwners.entries()) {
    if (owners.size !== 1) continue;
    const slug = [...owners][0];
    entries.push({
      slug,
      pattern,
      regex: toPatternRegex(pattern),
    });
  }
  return entries;
}

function getRawRelatedFundSlugs(signal: Partial<Signal> & Record<string, unknown>): string[] {
  const raw = signal.related_fund_slugs;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((value) => (typeof value === 'string' ? value.trim() : ''))
    .filter(Boolean);
}

export function resolveSignalFundSlugs(
  signal: Partial<Signal> & Record<string, unknown>,
  mentionEntries: FundMentionEntry[],
): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  const push = (slug?: string | null) => {
    const value = (slug || '').trim();
    if (!value || seen.has(value)) return;
    seen.add(value);
    result.push(value);
  };

  push(signal.fund_slug);
  for (const slug of getRawRelatedFundSlugs(signal)) push(slug);

  const sigAny = signal as Record<string, unknown>;
  const mentionText = normalizePhrase(
    [
      signal.title,
      signal.what_changed,
      typeof sigAny.diff_summary === 'string' ? sigAny.diff_summary : undefined,
      typeof sigAny.enriched_summary === 'string' ? sigAny.enriched_summary : undefined,
      typeof sigAny.title_original === 'string' ? sigAny.title_original : undefined,
      typeof sigAny.what_changed_original === 'string' ? sigAny.what_changed_original : undefined,
      typeof sigAny.enriched_summary_original === 'string' ? sigAny.enriched_summary_original : undefined,
    ]
      .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
      .join(' '),
  );

  if (mentionText) {
    for (const entry of mentionEntries) {
      if (entry.regex.test(mentionText)) {
        push(entry.slug);
      }
    }
  }

  return result;
}

export function resolveFundNamesForSlugs(
  slugs: string[],
  fundsBySlug: Map<string, FundReference>,
): string[] {
  return slugs.map((slug) => fundsBySlug.get(slug)?.name || slug.replace(/-/g, ' '));
}
