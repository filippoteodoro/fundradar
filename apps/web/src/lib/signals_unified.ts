/**
 * Unified signals loader for Fundradar
 *
 * Loads signals from Website Monitor (detected_signals.json)
 * Note: PEM signals are excluded as they provide historical data, not current updates
 */

import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import { getRepoRoot } from './repoRoot';
import type { Signal, SignalType } from '@fundradar/shared';
import { formatDate } from '@/lib/formatDate';
import {
  isGarbageSignal,
  buildKnownFundNames,
  cleanSignalTitle,
  cleanSignalText,
  normalizeSignalText,
  reclassifySignalType,
} from './signalProcessing';
import {
  buildFundMentionEntries,
  resolveSignalFundSlugs,
  resolveFundNamesForSlugs,
  type FundMentionEntry,
} from './signalFundTags';

// ─── Cross-language equivalence for dedup (hoisted from loadUnifiedSignals) ────
const CROSS_LANG: Record<string, string> = {
  investe: 'invests', investimento: 'investment', investimenti: 'investments',
  rileva: 'acquires', acquisisce: 'acquires', acquisizione: 'acquisition',
  cede: 'sells', cessione: 'sale', vendita: 'sale', venduto: 'sold', venduta: 'sold',
  chiude: 'closes', chiusura: 'closing', raccolta: 'fundraising', raccoglie: 'raises',
  lancio: 'launch', nasce: 'launches', lancia: 'launches',
  uscita: 'exit', fusione: 'merger', nomina: 'appointment',
  partecipazione: 'stake', societ\u00e0: 'company',
  fondo: 'fund', fondi: 'funds',
  nuovo: 'new', nuova: 'new', nuovi: 'new',
  operazione: 'deal', accordo: 'agreement',
  milioni: 'million', miliardi: 'billion',
};

function normalizeWordsXL(words: Set<string>): Set<string> {
  const result = new Set<string>();
  for (const w of words) result.add(CROSS_LANG[w] || w);
  return result;
}

const DEDUP_STRUCTURAL_WORDS = new Set([
  // PE/VC structural terms
  'sgr', 'capital', 'partners', 'group', 'investimenti', 'investment',
  'private', 'venture', 'fondo', 'fund', 'equity',
  // English stop-words (articles, prepositions, conjunctions, aux verbs).
  // Without these, coincidental function-word overlap (e.g. "in", "to", "the")
  // inflates similarity ratios and causes false-positive semantic dedup — notably
  // for CDP Venture Capital newsroom signals whose titles all start with "CDP
  // Venture Capital [SGR] …" and share many of these function words after fund-slug
  // stripping.
  'the', 'of', 'in', 'to', 'an', 'a', 'for', 'and', 'with', 'at', 'by',
  'from', 'on', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'has',
  'had', 'have', 'will', 'that', 'this', 'it', 'its', 'or', 'so',
]);

function parseSignalDate(s: { published_at?: string | null; observed_at?: string | null; created_at?: string | null }): number | null {
  const raw = s.published_at || s.observed_at || s.created_at || '';
  if (!raw) return null;
  const t = new Date(raw).getTime();
  return isNaN(t) ? null : t;
}

/**
 * Extended signal interface with additional website monitor fields
 */
export interface UnifiedSignal extends Signal {
  fund_name?: string;
  fund_slug?: string;
  related_fund_slugs?: string[];
  related_fund_names?: string[];
  page_category?: string;
  page_type?: string;
  diff_summary?: string;
  snapshot_id?: string;
  signal_types?: SignalType[];
}

interface WebsiteMonitorSignal {
  id: string;
  fund_id?: string;
  fund_slug?: string;
  signal_type: SignalType;
  title: string;
  what_changed: string;
  source_url: string;
  source_name: string;
  published_at: string | null;
  observed_at: string;
  created_at: string;
  page_category?: string;
  page_type?: string;
  diff_summary?: string;
  snapshot_id?: string;
  // Enriched fields (from Gemini)
  enriched_summary?: string;
  enriched_date?: string;
  enrichment_confidence?: string;
  // Rumor flag (from RSS monitor)
  is_rumor?: boolean;
  // Original Italian text (before DeepL translation)
  enriched_summary_original?: string;
  title_original?: string;
  what_changed_original?: string;
  related_fund_slugs?: string[];
  signal_types?: SignalType[];
}

interface DetectedSignalsFile {
  signals: WebsiteMonitorSignal[];
  signal_count: number;
}

interface Fund {
  id: string;
  slug: string;
  name: string;
}

interface Database {
  funds: Fund[];
}



/**
 * Load fund reference data from db.json (needed for fund name lookups)
 */
function loadFundsReference(): Fund[] {
  const repoRoot = getRepoRoot();
  const dbPath = join(repoRoot, 'data', 'db.json');

  if (!existsSync(dbPath)) {
    console.warn('Database not found at', dbPath);
    return [];
  }

  try {
    const data = readFileSync(dbPath, 'utf-8');
    const db: Database = JSON.parse(data);
    return db.funds || [];
  } catch (e) {
    console.error('Failed to load funds reference:', e);
    return [];
  }
}

/**
 * Load Website Monitor signals from detected_signals.json
 * Priority: enriched > filtered > raw
 */
function loadWebsiteMonitorSignals(): WebsiteMonitorSignal[] {
  const repoRoot = getRepoRoot();

  // Try enriched (filtered + AI summaries), then filtered, then raw
  const candidates = [
    join(repoRoot, 'data', 'derived', 'detected_signals_enriched.json'),
    join(repoRoot, 'data', 'derived', 'detected_signals_filtered.json'),
    join(repoRoot, 'data', 'derived', 'detected_signals.json'),
  ];

  let pathToUse: string | null = null;
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      pathToUse = candidate;
      break;
    }
  }

  if (!pathToUse) {
    console.warn('No signal files found');
    return [];
  }

  try {
    const data = readFileSync(pathToUse, 'utf-8');
    const file: DetectedSignalsFile = JSON.parse(data);
    return file.signals || [];
  } catch (e) {
    console.error('Failed to load Website Monitor signals:', e);
    return [];
  }
}

/**
 * Generate a content-based composite key for deduplication.
 * Uses source_url + display text + date (not signal id, which is always unique).
 */
function getCompositeKey(signal: UnifiedSignal): string {
  return `${signal.source_url}::${signal.what_changed}::${signal.published_at || ''}`;
}

function mergeRelatedFundTags(
  target: UnifiedSignal,
  source: UnifiedSignal,
  fundsBySlug: Map<string, Fund>,
): void {
  const mergedSlugs = [
    ...(target.related_fund_slugs || []),
    target.fund_slug || '',
    ...(source.related_fund_slugs || []),
    source.fund_slug || '',
  ]
    .map((slug) => slug.trim())
    .filter(Boolean)
    .filter((slug, index, arr) => arr.indexOf(slug) === index);

  const nameBySlug = new Map<string, string>();
  (target.related_fund_slugs || []).forEach((slug, idx) => {
    const name = target.related_fund_names?.[idx];
    if (name) nameBySlug.set(slug, name);
  });
  (source.related_fund_slugs || []).forEach((slug, idx) => {
    const name = source.related_fund_names?.[idx];
    if (name) nameBySlug.set(slug, name);
  });
  if (target.fund_slug && target.fund_name) nameBySlug.set(target.fund_slug, target.fund_name);
  if (source.fund_slug && source.fund_name) nameBySlug.set(source.fund_slug, source.fund_name);

  target.related_fund_slugs = mergedSlugs;
  target.related_fund_names = mergedSlugs.map((slug) => {
    return nameBySlug.get(slug) || fundsBySlug.get(slug)?.name || slug.replace(/-/g, ' ');
  });

  if (!target.fund_slug && source.fund_slug) {
    target.fund_slug = source.fund_slug;
    target.fund_name = source.fund_name;
  }
}

/**
 * Normalize a Website Monitor signal to the unified format
 * Uses enriched summary/date if available from Gemini enrichment
 */
function normalizeWebsiteMonitorSignal(
  sig: WebsiteMonitorSignal,
  funds: Fund[],
  mentionEntries: FundMentionEntry[],
  fundsBySlug: Map<string, Fund>,
): UnifiedSignal {
  const relatedFundSlugs = resolveSignalFundSlugs(
    sig as WebsiteMonitorSignal & Record<string, unknown>,
    mentionEntries,
  );
  const primaryFundSlug = sig.fund_slug || relatedFundSlugs[0] || '';

  // Try to find matching fund by slug
  const fund = primaryFundSlug
    ? funds.find((f) => f.slug === primaryFundSlug)
    : undefined;
  const relatedFundNames = resolveFundNamesForSlugs(relatedFundSlugs, fundsBySlug);

  // Single display text: prefer enriched summary, fall back to what_changed, then title
  // But skip enriched_summary if it's just restating the title (no added value)
  let rawText = sig.enriched_summary || '';
  if (rawText && sig.title) {
    const summaryWords = new Set(rawText.toLowerCase().replace(/[^\w\s]/g, '').split(/\s+/).filter(w => w.length >= 3));
    const titleWords = new Set(sig.title.toLowerCase().replace(/[^\w\s]/g, '').split(/\s+/).filter(w => w.length >= 3));
    if (titleWords.size > 0 && summaryWords.size > 0 && summaryWords.size < 25) {
      const overlap = [...summaryWords].filter(w => titleWords.has(w)).length;
      // Raised threshold from 0.7 to 0.9 to avoid suppressing genuine English translations
      // of Italian titles (audit H5: too-aggressive suppression dropped valid enriched summaries)
      if (overlap / Math.min(summaryWords.size, titleWords.size) >= 0.9 &&
          summaryWords.size <= titleWords.size * 1.3) {
        // Don't suppress if summary is an English translation of an Italian title
        // (they share proper nouns but the summary adds English readability)
        const italianWords = /\b(acquisisce|nominato|entra|avvia|rileva|investe|finanziamento|raccoglie|sottoscritto|operazione|milioni|miliardi)\b/i;
        const titleIsItalian = italianWords.test(sig.title);
        const summaryIsEnglish = !italianWords.test(rawText) && /\b(acquires|appointed|joins|raises|launches|invests|closes|announces)\b/i.test(rawText);
        if (!(titleIsItalian && summaryIsEnglish)) {
          rawText = ''; // Redundant — fall through to what_changed/title
        }
      }
    }
  }
  if (!rawText) rawText = sig.what_changed || sig.title || '';
  let displayText = cleanSignalText(cleanSignalTitle(rawText));

  // Strip fund name prefix — the UI shows fund name as a header link above the card
  if (fund) {
    const escaped = fund.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    displayText = displayText.replace(new RegExp('^\\s*' + escaped + '\\s*:\\s*', 'i'), '').trim();
  }
  // Also strip slug-derived name patterns (enricher sometimes uses slug → title case as label)
  if (sig.fund_slug) {
    const slugName = sig.fund_slug.replace(/-/g, ' ');
    const escapedSlug = slugName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    displayText = displayText.replace(new RegExp('^\\s*' + escapedSlug + '\\s*:\\s*', 'i'), '').trim();
  }
  // Strip source name prefix — the UI shows source as a separate label
  if (sig.source_name) {
    const escapedSource = sig.source_name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    displayText = displayText.replace(new RegExp('^\\s*' + escapedSource + '\\s*:\\s*', 'i'), '').trim();
    // CamelCase split: "FinanceCommunity" → "Finance Community"
    const camelSplit = sig.source_name.replace(/([a-z])([A-Z])/g, '$1 $2');
    if (camelSplit !== sig.source_name) {
      const escapedCamel = camelSplit.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      displayText = displayText.replace(new RegExp('^\\s*' + escapedCamel + '\\s*:\\s*', 'i'), '').trim();
    }
  }
  // Strip fund_name from signal itself (may differ from fund.name for multi-fund signals)
  const sigAny = sig as unknown as Record<string, unknown>;
  if (sigAny.fund_name && typeof sigAny.fund_name === 'string') {
    const rawFundName = sigAny.fund_name as string;
    if (rawFundName !== fund?.name) {
      const escapedRaw = rawFundName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      displayText = displayText.replace(new RegExp('^\\s*' + escapedRaw + '\\s*:\\s*', 'i'), '').trim();
    }
  }

  // Generic single-label prefix stripping: "CompanyName: rest" → "CompanyName rest" or just "Rest"
  // Catches entity names the specific strips above missed (portfolio company names, etc.)
  const labelMatch = displayText.match(/^([A-Za-z0-9&'()./\-\u00C0-\u024F ]{2,60})\s*:\s*(.+)$/s);
  if (labelMatch) {
    const label = labelMatch[1].trim();
    const rest = labelMatch[2].trim();
    const labelWords = label.split(/\s+/);
    if (labelWords.length <= 5 && rest.length >= 10) {
      const isTitleCase = labelWords.every(w =>
        w.length <= 1 || /^[A-Z\u00C0-\u024F]/.test(w) || ['di','del','della','e','and','the','for','in','of','up'].includes(w.toLowerCase())
      );
      if (isTitleCase) {
        if (/^[a-z]/.test(rest) || /^(the |a |an |to |for )/i.test(rest)) {
          displayText = `${label} ${rest}`;
        } else {
          displayText = rest.charAt(0).toUpperCase() + rest.slice(1);
        }
      }
    }
  }

  // Sentence-aware truncation: never cut mid-sentence
  if (displayText.length > 500) {
    const trimmed = displayText.slice(0, 500);
    // Find the last sentence boundary (period followed by space or end)
    let lastSentence = -1;
    for (let i = trimmed.length - 1; i > 0; i--) {
      if (trimmed[i] === '.' && (i === trimmed.length - 1 || trimmed[i + 1] === ' ')) {
        lastSentence = i;
        break;
      }
    }
    if (lastSentence > 150) {
      displayText = trimmed.slice(0, lastSentence + 1);
    } else {
      // No good sentence boundary — fall back to word boundary
      const wordTrimmed = trimmed.trimEnd();
      const lastSpace = wordTrimmed.lastIndexOf(' ');
      displayText = (lastSpace > 200 ? wordTrimmed.slice(0, lastSpace) : wordTrimmed) + '...';
    }
  }

  // Use enriched date or published_at, normalized to YYYY-MM-DD
  const displayDate = formatDate(sig.enriched_date || sig.published_at) || null;

  // Reclassify mistyped signals (e.g. fundraise_announced → deal_announced)
  // IMPORTANT: Use original Italian title/what_changed for classification (NOT English enriched_summary).
  // The reclassifier has Italian-specific patterns (vendere, ceduto, etc.) that fail against English text,
  // and English words like "acquire" (in outsourcing context) cause false deal matches.
  const newType = reclassifySignalType({
    ...sig,
    fund_id: fund?.id || sig.fund_id || '',
    source_url_status: 'ok',
    title: sig.title || '',
    what_changed: sig.what_changed || '',
  } as Signal);

  return {
    id: sig.id,
    fund_id: fund?.id || sig.fund_id || '',
    signal_type: newType || sig.signal_type,
    title: displayText,
    what_changed: displayText,
    source_url: sig.source_url,
    source_name: sig.source_name,
    source_url_status: 'ok',
    published_at: displayDate,
    observed_at: sig.observed_at,
    created_at: sig.created_at,
    // Extended fields
    fund_name: fund?.name || primaryFundSlug.replace(/-/g, ' ') || 'Unknown Fund',
    fund_slug: primaryFundSlug || fund?.slug || '',
    related_fund_slugs: relatedFundSlugs,
    related_fund_names: relatedFundNames,
    page_category: sig.page_category || 'OTHER',
    page_type: sig.page_type,
    diff_summary: sig.diff_summary,
    snapshot_id: sig.snapshot_id,
    is_rumor: sig.is_rumor,
    signal_types: sig.signal_types,
  };
}

/**
 * Load fund priority scores from LinkedIn prioritized file
 * Returns a map of fund_slug -> priority_score
 */
function loadFundPriorityScores(): Record<string, number> {
  const repoRoot = getRepoRoot();
  const filePath = join(repoRoot, 'data', 'derived', 'linkedin', 'fund_linkedin_urls_prioritized.json');

  if (!existsSync(filePath)) {
    console.warn('Fund priority file not found at', filePath);
    return {};
  }

  try {
    const data = readFileSync(filePath, 'utf-8');
    const parsed = JSON.parse(data);
    const scores: Record<string, number> = {};
    for (const company of parsed.companies || []) {
      if (company.slug && typeof company.priority_score === 'number') {
        scores[company.slug] = company.priority_score;
      }
    }
    return scores;
  } catch (e) {
    console.error('Failed to load fund priority scores:', e);
    return {};
  }
}

let cachedResult: { signals: UnifiedSignal[]; fundPriorityScores: Record<string, number> } | null = null;

/**
 * Load signals from Website Monitor only
 * PEM signals are excluded as they provide historical data, not current updates
 */
const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

export function countSignalsLast30Days(signals: Pick<UnifiedSignal, 'published_at' | 'observed_at'>[]): number {
  const cutoff = Date.now() - THIRTY_DAYS_MS;
  return signals.filter((s) => {
    const ts = s.published_at || s.observed_at;
    return ts ? new Date(ts).getTime() > cutoff : false;
  }).length;
}

export function loadUnifiedSignals(): { signals: UnifiedSignal[]; fundPriorityScores: Record<string, number> } {
  if (cachedResult) return cachedResult;
  // Load funds for reference (needed for fund names)
  const funds = loadFundsReference();
  const fundsBySlug = new Map(funds.map((f) => [f.slug, f]));
  const mentionEntries = buildFundMentionEntries(
    funds.map((f) => ({ slug: f.slug, name: f.name })),
  );

  // Build composite fund priority scores: AUM (log-scaled) + LinkedIn priority + Italy focus
  const linkedInScores = loadFundPriorityScores();
  const fundPriorityScores: Record<string, number> = {};
  for (const fund of funds) {
    if (!fund.slug) continue;
    const linkedIn = linkedInScores[fund.slug] || 0;
    const aum = (fund as any).aum_eur || 0;
    // Log-scale AUM: Blackstone(1T)→40, KKR(555B)→38, mid-cap(5B)→25, small(500M)→18
    const aumScore = aum > 0 ? Math.max(0, Math.log10(aum) - 7) * 10 : 0;
    // Italy-focused funds get a bonus (SGR/SICAF/SIM or Italy in geographies)
    const geos: string[] = (fund as any).geographies || [];
    const name = fund.name || '';
    const isItalyFocused = geos.includes('Italy') || /\b(SGR|SICAF|SIM)\b/i.test(name);
    const italyBonus = isItalyFocused ? 15 : 0;
    fundPriorityScores[fund.slug] = (linkedIn * 0.3) + aumScore + italyBonus;
  }

  // Load only Website Monitor signals (no PEM)
  const websiteMonitorSignals = loadWebsiteMonitorSignals();

  // Build known fund names for misattribution detection (auto-derived from db.json)
  const knownFundNames = buildKnownFundNames(funds);

  // Normalize Website Monitor signals, then filter garbage
  const normalizedWebMonitor = websiteMonitorSignals
    .filter((s) => s.signal_type !== 'website_change')
    .map((s) => normalizeWebsiteMonitorSignal(s, funds, mentionEntries, fundsBySlug))
    .filter((s) => !isGarbageSignal(s, knownFundNames));

  // Dedupe using composite keys and normalized content
  const byCompositeKey = new Map<string, UnifiedSignal>();
  const byContentKey = new Map<string, UnifiedSignal>();
  const byCrossFundKey = new Map<string, UnifiedSignal>();
  const unified: UnifiedSignal[] = [];

  for (const signal of normalizedWebMonitor) {
    const key = getCompositeKey(signal);
    const normText = normalizeSignalText(signal.what_changed || '');
    const contentKey = `${normText}::${signal.published_at || ''}`;
    // Cross-fund dedup: identify the same article published under multiple fund slugs
    // and collapse it into one signal (keeping all fund tags).
    // Bug guard: when what_changed is empty, fall back to title so that signals from
    // the same URL with *different* story titles (e.g. CDP newsroom) are NOT collapsed.
    // Without the fallback, all URL-same + empty-what_changed signals share key "url::"
    // and 34+ legitimate CDP signals were silently deduped to 1.
    const normTextForKey = normText || normalizeSignalText(signal.title || '');
    // Skip cross-fund dedup when there is genuinely no identifying text — the composite
    // key (url::what_changed::date) is still the primary collision guard.
    const crossFundKey = normTextForKey ? `${signal.source_url}::${normTextForKey}` : null;
    const existing =
      (crossFundKey ? byCrossFundKey.get(crossFundKey) : undefined) ||
      byCompositeKey.get(key) ||
      byContentKey.get(contentKey);
    if (existing) {
      mergeRelatedFundTags(existing, signal, fundsBySlug);
      continue;
    }

    byCompositeKey.set(key, signal);
    byContentKey.set(contentKey, signal);
    if (crossFundKey) byCrossFundKey.set(crossFundKey, signal);
    unified.push(signal);
  }

  // Cross-language, structural words, and normalizeWordsXL are hoisted to module scope

  // Semantic dedup: suppress near-duplicate signals about same deal from different sources
  // Tiered thresholds: 40% overlap within 3 days, 50% within 7 days, 60% with no date
  const semanticDeduped: UnifiedSignal[] = [];
  interface KeptEntry { words: Set<string>; date: number | null; }
  const fundKept = new Map<string, KeptEntry[]>();

  for (const signal of unified) {
    const slug = signal.fund_slug || '';
    // Words to strip: fund name words + structural PE/VC terms
    const fundNameWords = new Set([
      ...slug.replace(/-/g, ' ').split(/\s+/).filter(Boolean),
      ...DEDUP_STRUCTURAL_WORDS,
    ]);
    const titleNorm = normalizeSignalText(signal.what_changed || '');
    const words = new Set(titleNorm.split(/\s+/).filter(Boolean));
    if (words.size < 3) {
      semanticDeduped.push(signal);
      continue;
    }

    // Strip fund name / structural words for overlap calculation
    const wordsNF = new Set([...words].filter(w => !fundNameWords.has(w)));

    const sigDate = parseSignalDate(signal);
    const existing = fundKept.get(slug) || [];
    let isDup = false;
    for (const entry of existing) {
      // Use fund-name-stripped word sets for overlap to avoid false dedup
      const entryWordsNF = new Set([...entry.words].filter(w => !fundNameWords.has(w)));
      let overlapNative = 0;
      for (const w of wordsNF) { if (entryWordsNF.has(w)) overlapNative++; }
      const wordsNFXL = normalizeWordsXL(wordsNF);
      const entryWordsNFXL = normalizeWordsXL(entryWordsNF);
      let overlapXL = 0;
      for (const w of wordsNFXL) { if (entryWordsNFXL.has(w)) overlapXL++; }
      const overlap = Math.max(overlapNative, overlapXL);
      const shorter = Math.min(wordsNF.size, entryWordsNF.size);
      if (shorter === 0) continue;
      const ratio = overlap / shorter;

      // Date proximity check
      let dayDiff: number | null = null;
      if (sigDate !== null && entry.date !== null) {
        dayDiff = Math.abs(sigDate - entry.date) / (1000 * 60 * 60 * 24);
      }

      // Tighter threshold for close dates (within 3 days): 40% overlap
      if (dayDiff !== null && dayDiff <= 3 && ratio >= 0.4) {
        isDup = true;
        break;
      }
      // Standard threshold: 50% overlap within 7 days
      if (ratio >= 0.5 && (dayDiff === null || dayDiff <= 7)) {
        if (dayDiff !== null || ratio >= 0.6) {
          isDup = true;
          break;
        }
      }
    }

    if (!isDup) {
      existing.push({ words, date: sigDate });
      fundKept.set(slug, existing);
      semanticDeduped.push(signal);
    }
  }

  // Sort by effective date descending: published_at is authoritative; signals
  // with no confirmed event date get a 7-day penalty so they don't rank above
  // signals whose event date is known.
  const PENALTY_MS = 60 * 60 * 1000; // 1 hour — enough to rank below same-day confirmed-date signals
  semanticDeduped.sort((a, b) => {
    const tsA = a.published_at
      ? new Date(a.published_at).getTime()
      : new Date(a.observed_at || a.created_at || '').getTime() - PENALTY_MS;
    const tsB = b.published_at
      ? new Date(b.published_at).getTime()
      : new Date(b.observed_at || b.created_at || '').getTime() - PENALTY_MS;
    return tsB - tsA;
  });

  cachedResult = { signals: semanticDeduped, fundPriorityScores };
  return cachedResult;
}
