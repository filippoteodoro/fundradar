/**
 * Build weekly digest outputs for Fundradar subscribers.
 *
 * Output files:
 * - latest_digest.txt    (plain text)
 * - latest_recipients.csv
 * - latest_digest_meta.json
 * - sent_log.json        (unless --dry-run)
 * - Applies digest-only suppression list from data/digest_unsubscribed_emails.json
 *
 * Selection rule:
 * - Compute an effective signal date:
 *   - published_at, if present
 *   - otherwise observed_at
 * - Include only if that effective date is in [window_from, window_to)
 * - Exclude already-sent signals from sent_log.json
 *
 * Ranking:
 * - Event-first ranking based on signals-feed style importance.
 * - Multi-fund events are emitted once with all related funds listed.
 * - Selection still caps by primary fund for diversity.
 */

import { config } from 'dotenv';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { basename, dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';
import Stripe from 'stripe';

// Load .env from repo root
const __dirname_local = dirname(fileURLToPath(import.meta.url));
config({ path: join(__dirname_local, '..', '.env') });

interface CliOptions {
  fromIso?: string;
  toIso?: string;
  days: number;
  maxSignals: number;
  maxPerFund: number;
  timezone: string;
  dryRun: boolean;
}

interface RawSignal {
  id?: unknown;
  fund_slug?: unknown;
  related_fund_slugs?: unknown;
  signal_type?: unknown;
  title?: unknown;
  what_changed?: unknown;
  enriched_summary?: unknown;
  source_url?: unknown;
  source_name?: unknown;
  published_at?: unknown;
  observed_at?: unknown;
  created_at?: unknown;
  quality_score?: unknown;
  evidence_score?: unknown;
  confidence_score?: unknown;
  relevance_score?: unknown;
  italy_relevant?: unknown;
}

interface SignalContainer {
  signals?: RawSignal[];
}

interface FundDbRecord {
  slug?: unknown;
  name?: unknown;
  aum_eur?: unknown;
}

interface DbFile {
  funds?: FundDbRecord[];
}

interface PriorityRecord {
  slug?: unknown;
  priority_score?: unknown;
}

interface PriorityFile {
  companies?: PriorityRecord[];
}

interface SentLogEntry {
  signal_key: string;
  first_sent_at: string;
  last_sent_at: string;
  times_sent: number;
  last_digest_id: string;
}

interface SentLog {
  generated_at: string;
  entries: SentLogEntry[];
}

interface FundProfile {
  slug: string;
  name: string;
  aumEur: number | null;
  priorityScore: number;
}

interface DigestSignal {
  id: string;
  key: string;
  primaryFundSlug: string;
  primaryFundName: string;
  relatedFundSlugs: string[];
  relatedFundNames: string[];
  signalType: string;
  title: string;
  sourceUrl: string;
  sourceName: string;
  publishedAtRaw: string | null;
  observedAtRaw: string | null;
  publishedDate: Date | null;
  observedDate: Date | null;
  createdDate: Date | null;
  relevanceNorm: number;
  italyRelevant: boolean | null;
  importanceScore: number;
}

interface DigestMeta {
  digest_id: string;
  generated_at: string;
  source_file: string | null;
  source_file_path: string | null;
  window_from: string;
  window_to: string;
  timezone: string;
  days: number;
  max_signals: number;
  max_per_fund: number;
  ranking_mode: string;
  signals_window_matched: number;
  signals_after_in_batch_dedupe: number;
  signals_already_sent: number;
  signals_included: number;
  funds_included: number;
  recipients_active: number;
  recipients_suppressed: number;
  recipients_sendable: number;
  dry_run: boolean;
}

interface SuppressionList {
  updated_at?: string;
  emails?: string[];
}

const __dirname = dirname(fileURLToPath(import.meta.url));

function printUsage(): void {
  console.log('Usage: pnpm -F scripts digest:build [options]');
  console.log('');
  console.log('Options:');
  console.log('  --from <ISO>          Window start (inclusive), e.g. 2026-02-01T00:00:00Z');
  console.log('  --to <ISO>            Window end (exclusive), defaults to now UTC');
  console.log('  --days <N>            Lookback days when --from is omitted (default: 7)');
  console.log('  --max-signals <N>     Max total signals in digest (default: 25)');
  console.log('  --max-per-fund <N>    Max signals per fund in first pass (default: 2)');
  console.log('  --timezone <IANA>     Display timezone (default: UTC)');
  console.log('  --dry-run             Build outputs but do not update sent_log.json');
  console.log('  --help, -h            Show this help');
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    days: 7,
    maxSignals: 25,
    maxPerFund: 2,
    timezone: 'UTC',
    dryRun: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === '--') {
      continue;
    } else if (arg === '--help' || arg === '-h') {
      printUsage();
      process.exit(0);
    } else if (arg === '--dry-run') {
      options.dryRun = true;
    } else if (arg === '--from' && i + 1 < argv.length) {
      options.fromIso = argv[i + 1];
      i += 1;
    } else if (arg.startsWith('--from=')) {
      options.fromIso = arg.split('=', 2)[1];
    } else if (arg === '--to' && i + 1 < argv.length) {
      options.toIso = argv[i + 1];
      i += 1;
    } else if (arg.startsWith('--to=')) {
      options.toIso = arg.split('=', 2)[1];
    } else if (arg === '--days' && i + 1 < argv.length) {
      options.days = parseInt(argv[i + 1], 10);
      i += 1;
    } else if (arg.startsWith('--days=')) {
      options.days = parseInt(arg.split('=', 2)[1], 10);
    } else if (arg === '--max-signals' && i + 1 < argv.length) {
      options.maxSignals = parseInt(argv[i + 1], 10);
      i += 1;
    } else if (arg.startsWith('--max-signals=')) {
      options.maxSignals = parseInt(arg.split('=', 2)[1], 10);
    } else if (arg === '--max-per-fund' && i + 1 < argv.length) {
      options.maxPerFund = parseInt(argv[i + 1], 10);
      i += 1;
    } else if (arg.startsWith('--max-per-fund=')) {
      options.maxPerFund = parseInt(arg.split('=', 2)[1], 10);
    } else if (arg === '--timezone' && i + 1 < argv.length) {
      options.timezone = argv[i + 1];
      i += 1;
    } else if (arg.startsWith('--timezone=')) {
      options.timezone = arg.split('=', 2)[1];
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!Number.isFinite(options.days) || options.days <= 0) {
    throw new Error('--days must be a positive integer');
  }
  if (!Number.isFinite(options.maxSignals) || options.maxSignals <= 0) {
    throw new Error('--max-signals must be a positive integer');
  }
  if (!Number.isFinite(options.maxPerFund) || options.maxPerFund <= 0) {
    throw new Error('--max-per-fund must be a positive integer');
  }

  // Validate timezone
  // eslint-disable-next-line no-new
  new Intl.DateTimeFormat('en-CA', { timeZone: options.timezone });

  return options;
}

function parseIsoDateTime(value: string, label: string): Date {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error(`Invalid ${label} value: ${value}`);
  }
  return date;
}

function parseSignalDate(value: unknown): Date | null {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return null;
  }
  const trimmed = value.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    const day = new Date(`${trimmed}T00:00:00Z`);
    return Number.isNaN(day.getTime()) ? null : day;
  }
  const date = new Date(trimmed);
  return Number.isNaN(date.getTime()) ? null : date;
}

function inWindow(value: Date | null, from: Date, to: Date): boolean {
  if (!value) return false;
  const ts = value.getTime();
  return ts >= from.getTime() && ts < to.getTime();
}

function cleanText(value: unknown): string {
  if (typeof value !== 'string') return '';
  return value.replace(/\s+/g, ' ').trim();
}

function toSlug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function normalizeForKey(value: string): string {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

function parseNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function parseBool(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const v = value.toLowerCase().trim();
    if (v === 'true') return true;
    if (v === 'false') return false;
  }
  return null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeRelevance(relevanceScore: number | null, italyRelevant: boolean | null): number {
  if (relevanceScore !== null) {
    // Accept either 0..1 or 0..100
    if (relevanceScore > 1) return clamp(relevanceScore / 100, 0, 1);
    return clamp(relevanceScore, 0, 1);
  }
  if (italyRelevant === true) return 1;
  if (italyRelevant === false) return 0;
  return 0.5;
}

function getTypeBonus(signalType: string): number {
  const typeBonus: Record<string, number> = {
    deal_announced: 15,
    exit_announced: 15,
    fundraise_closed: 12,
    fund_launch: 10,
    fundraise_announced: 8,
    people_move: 5,
    job_posting: 3,
  };
  return typeBonus[signalType] ?? 0;
}

function getPrimaryDate(signal: DigestSignal): Date | null {
  return signal.publishedDate || signal.observedDate || signal.createdDate || null;
}

function getPrimaryTimestamp(signal: DigestSignal): number {
  const date = getPrimaryDate(signal);
  return date ? date.getTime() : 0;
}

function buildSignalKey(signal: {
  sourceUrl: string;
  title: string;
  publishedDate: Date | null;
}): string {
  const publishedPart = signal.publishedDate ? signal.publishedDate.toISOString().slice(0, 10) : 'null';
  return [
    normalizeForKey(signal.sourceUrl),
    normalizeForKey(signal.title),
    publishedPart,
  ].join('::');
}

function buildLegacySignalKey(signal: {
  sourceUrl: string;
  title: string;
  publishedDate: Date | null;
  fundSlug: string;
}): string {
  const publishedPart = signal.publishedDate ? signal.publishedDate.toISOString().slice(0, 10) : 'null';
  return [
    normalizeForKey(signal.sourceUrl),
    normalizeForKey(signal.title),
    publishedPart,
    normalizeForKey(signal.fundSlug),
  ].join('::');
}

function formatDay(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone,
  }).format(date);
}

function prettifyFundSlug(slug: string): string {
  const words = slug.split('-').filter(Boolean);
  if (words.length === 0) return 'Unknown Fund';
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function parseRelatedFundSlugs(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const related: string[] = [];
  const seen = new Set<string>();
  for (const raw of value) {
    const slug = toSlug(cleanText(raw));
    if (!slug || seen.has(slug)) continue;
    seen.add(slug);
    related.push(slug);
  }
  return related;
}

function mergeFundLists(
  aSlugs: string[],
  aNames: string[],
  bSlugs: string[],
  bNames: string[],
): { slugs: string[]; names: string[] } {
  const slugs: string[] = [];
  const names: string[] = [];
  const seen = new Set<string>();
  const nameBySlug = new Map<string, string>();

  for (let i = 0; i < aSlugs.length; i += 1) {
    const slug = aSlugs[i];
    if (!slug || seen.has(slug)) continue;
    seen.add(slug);
    slugs.push(slug);
    const name = aNames[i];
    if (name) nameBySlug.set(slug, name);
  }

  for (let i = 0; i < bSlugs.length; i += 1) {
    const slug = bSlugs[i];
    if (!slug) continue;
    const name = bNames[i];
    if (name && !nameBySlug.has(slug)) nameBySlug.set(slug, name);
    if (seen.has(slug)) continue;
    seen.add(slug);
    slugs.push(slug);
  }

  for (const slug of slugs) {
    names.push(nameBySlug.get(slug) || prettifyFundSlug(slug));
  }

  return { slugs, names };
}

function normalizeRelatedFundNames(signal: DigestSignal): DigestSignal {
  const merged = mergeFundLists(
    signal.relatedFundSlugs,
    signal.relatedFundNames,
    signal.relatedFundSlugs,
    signal.relatedFundNames,
  );
  return {
    ...signal,
    relatedFundSlugs: merged.slugs,
    relatedFundNames: merged.names,
  };
}

function mergeItalyRelevant(a: boolean | null, b: boolean | null): boolean | null {
  if (a === true || b === true) return true;
  if (a === false && b === false) return false;
  if (a === null) return b;
  if (b === null) return a;
  return null;
}

function getDisplayDate(signal: DigestSignal, timeZone: string): string {
  if (signal.publishedDate) {
    return formatDay(signal.publishedDate, timeZone);
  }
  if (signal.observedDate) {
    return `${formatDay(signal.observedDate, timeZone)} (observed)`;
  }
  if (signal.publishedAtRaw && signal.publishedAtRaw.length > 0) {
    return signal.publishedAtRaw;
  }
  if (signal.observedAtRaw && signal.observedAtRaw.length > 0) {
    return `${signal.observedAtRaw} (observed)`;
  }
  return 'n/a';
}

function getSourceDomain(sourceUrl: string): string {
  try {
    return new URL(sourceUrl).hostname.replace(/^www\./, '');
  } catch {
    return sourceUrl;
  }
}

function toMarkdownLink(label: string, href: string): string {
  const safeLabel = label.replace(/\[/g, '\\[').replace(/\]/g, '\\]');
  const safeHref = href.replace(/\)/g, '%29');
  return `[${safeLabel}](${safeHref})`;
}

function wrapWithIndent(
  text: string,
  firstPrefix: string,
  nextPrefix: string,
  maxWidth = 110,
): string[] {
  const words = text.split(/\s+/).filter((word) => word.length > 0);
  if (words.length === 0) {
    return [firstPrefix.trimEnd()];
  }

  const lines: string[] = [];
  let prefix = firstPrefix;
  let current = '';

  for (const word of words) {
    const candidate = current.length > 0 ? `${current} ${word}` : word;
    const wouldOverflow = prefix.length + candidate.length > maxWidth;
    if (!wouldOverflow || current.length === 0) {
      current = candidate;
      continue;
    }

    lines.push(`${prefix}${current}`);
    prefix = nextPrefix;
    current = word;
  }

  lines.push(`${prefix}${current}`);
  return lines;
}

function resolveProjectRoot(): string {
  const candidates = [
    process.cwd(),
    join(process.cwd(), '..'),
    join(__dirname, '..'),
    join(__dirname, '..', '..'),
  ];

  for (const candidate of candidates) {
    const absolute = resolve(candidate);
    if (existsSync(join(absolute, 'data')) && existsSync(join(absolute, 'scripts'))) {
      return absolute;
    }
  }

  throw new Error('Could not resolve project root (expected data/ and scripts/ directories).');
}

function loadJsonFile<T>(path: string): T | null {
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as T;
  } catch (error) {
    throw new Error(`Failed to parse JSON at ${path}: ${(error as Error).message}`);
  }
}

function loadFundProfiles(projectRoot: string): Record<string, FundProfile> {
  const profiles: Record<string, FundProfile> = {};

  const dbPath = join(projectRoot, 'data', 'db.json');
  const db = loadJsonFile<DbFile>(dbPath);
  for (const item of db?.funds ?? []) {
    const slugRaw = cleanText(item.slug);
    if (!slugRaw) continue;
    const slug = toSlug(slugRaw);
    if (!slug) continue;
    const name = cleanText(item.name) || prettifyFundSlug(slug);
    const aum = parseNumber(item.aum_eur);
    profiles[slug] = {
      slug,
      name,
      aumEur: aum && aum > 0 ? aum : null,
      priorityScore: 0,
    };
  }

  const priorityPath = join(projectRoot, 'data', 'derived', 'linkedin', 'fund_linkedin_urls_prioritized.json');
  const priority = loadJsonFile<PriorityFile>(priorityPath);
  for (const item of priority?.companies ?? []) {
    const slugRaw = cleanText(item.slug);
    if (!slugRaw) continue;
    const slug = toSlug(slugRaw);
    if (!slug) continue;
    const priorityScore = parseNumber(item.priority_score) ?? 0;
    if (!profiles[slug]) {
      profiles[slug] = {
        slug,
        name: prettifyFundSlug(slug),
        aumEur: null,
        priorityScore,
      };
    } else {
      profiles[slug].priorityScore = priorityScore;
    }
  }

  return profiles;
}

async function loadActiveRecipients(): Promise<string[]> {
  const secretKey = process.env.STRIPE_SECRET_KEY;
  if (!secretKey) {
    console.warn('STRIPE_SECRET_KEY not set — no recipients loaded. Set it in .env to pull subscribers from Stripe.');
    return [];
  }

  const stripe = new Stripe(secretKey);
  const unique = new Set<string>();
  let hasMore = true;
  let startingAfter: string | undefined;

  while (hasMore) {
    const params: Stripe.SubscriptionListParams = {
      status: 'active',
      limit: 100,
      expand: ['data.customer'],
    };
    if (startingAfter) params.starting_after = startingAfter;

    const subscriptions = await stripe.subscriptions.list(params);

    for (const sub of subscriptions.data) {
      const customer = sub.customer;
      if (typeof customer === 'string') continue;
      if ('deleted' in customer && customer.deleted) continue;
      const email = customer.email;
      if (email) unique.add(email.trim().toLowerCase());
    }

    hasMore = subscriptions.has_more;
    if (subscriptions.data.length > 0) {
      startingAfter = subscriptions.data[subscriptions.data.length - 1].id;
    }
  }

  console.log(`  Loaded ${unique.size} active subscribers from Stripe`);
  return Array.from(unique).sort();
}

function loadSuppressedRecipients(projectRoot: string): Set<string> {
  const suppressionPath = join(projectRoot, 'data', 'digest_unsubscribed_emails.json');
  const parsed = loadJsonFile<SuppressionList | string[]>(suppressionPath);
  if (!parsed) return new Set();

  const rawEmails = Array.isArray(parsed) ? parsed : parsed.emails;
  if (!Array.isArray(rawEmails)) return new Set();

  const suppressed = new Set<string>();
  for (const value of rawEmails) {
    if (typeof value !== 'string') continue;
    const email = value.trim().toLowerCase();
    if (!email) continue;
    suppressed.add(email);
  }
  return suppressed;
}

function loadSignalsFile(derivedDir: string): { filePath: string | null; fileName: string | null; signals: RawSignal[] } {
  const candidates = [
    join(derivedDir, 'detected_signals_enriched.json'),
    join(derivedDir, 'detected_signals_filtered.json'),
    join(derivedDir, 'detected_signals.json'),
  ];

  for (const candidate of candidates) {
    if (!existsSync(candidate)) continue;
    const parsed = loadJsonFile<SignalContainer | RawSignal[]>(candidate);
    if (!parsed) continue;
    if (Array.isArray(parsed)) {
      return { filePath: candidate, fileName: basename(candidate), signals: parsed };
    }
    if (Array.isArray(parsed.signals)) {
      return { filePath: candidate, fileName: basename(candidate), signals: parsed.signals };
    }
  }

  return { filePath: null, fileName: null, signals: [] };
}

function normalizeCandidates(
  rawSignals: RawSignal[],
  from: Date,
  to: Date,
  fundProfiles: Record<string, FundProfile>,
): DigestSignal[] {
  const results: DigestSignal[] = [];

  for (const raw of rawSignals) {
    const sourceUrl = cleanText(raw.source_url);
    if (!sourceUrl) continue;

    const title = cleanText(raw.title) || cleanText(raw.enriched_summary) || cleanText(raw.what_changed);
    if (!title) continue;

    const rawFundSlug = toSlug(cleanText(raw.fund_slug)) || 'unknown-fund';
    const relatedFundSlugsRaw = parseRelatedFundSlugs(raw.related_fund_slugs);
    const relatedFundSlugs = mergeFundLists(
      [rawFundSlug],
      [fundProfiles[rawFundSlug]?.name || prettifyFundSlug(rawFundSlug)],
      relatedFundSlugsRaw,
      relatedFundSlugsRaw.map((slug) => fundProfiles[slug]?.name || prettifyFundSlug(slug)),
    ).slugs;
    const primaryFundSlug = relatedFundSlugs[0] || rawFundSlug;
    const relatedFundNames = relatedFundSlugs.map((slug) => {
      return fundProfiles[slug]?.name || prettifyFundSlug(slug);
    });
    const primaryFundName = relatedFundNames[0] || prettifyFundSlug(primaryFundSlug);
    const fundPriority = relatedFundSlugs.reduce((max, slug) => {
      const priority = fundProfiles[slug]?.priorityScore ?? 0;
      return Math.max(max, priority);
    }, 0);

    const signalType = cleanText(raw.signal_type) || 'other';
    const id = cleanText(raw.id) || buildSignalKey({ sourceUrl, title, publishedDate: null });

    const publishedAtRaw = typeof raw.published_at === 'string' ? raw.published_at.trim() : null;
    const observedAtRaw = typeof raw.observed_at === 'string' ? raw.observed_at.trim() : null;
    const createdAtRaw = typeof raw.created_at === 'string' ? raw.created_at.trim() : null;

    const publishedDate = parseSignalDate(publishedAtRaw);
    const observedDate = parseSignalDate(observedAtRaw);
    const createdDate = parseSignalDate(createdAtRaw);

    const hasPublishedAt = publishedAtRaw !== null && publishedAtRaw.length > 0;
    const effectiveDate = hasPublishedAt ? publishedDate : observedDate;
    const include = inWindow(effectiveDate, from, to);
    if (!include) continue;

    const quality = parseNumber(raw.quality_score) ?? 50;
    const evidence = parseNumber(raw.evidence_score) ?? 0;
    const confidence = parseNumber(raw.confidence_score) ?? 0.5;
    const italyRelevant = parseBool(raw.italy_relevant);
    const relevanceNorm = normalizeRelevance(parseNumber(raw.relevance_score), italyRelevant);

    // Keep the same core scoring shape used on /signals, then add relevance boosts.
    let importanceScore =
      quality +
      (evidence * 4) +
      getTypeBonus(signalType) +
      (fundPriority * 0.5) +
      (confidence * 10);

    importanceScore += relevanceNorm * 12;
    if (italyRelevant === true) importanceScore += 5;
    if (italyRelevant === false) importanceScore -= 5;

    const key = buildSignalKey({
      sourceUrl,
      title,
      publishedDate,
    });

    results.push({
      id,
      key,
      primaryFundSlug,
      primaryFundName,
      relatedFundSlugs,
      relatedFundNames,
      signalType,
      title,
      sourceUrl,
      sourceName: cleanText(raw.source_name) || 'Unknown source',
      publishedAtRaw,
      observedAtRaw,
      publishedDate,
      observedDate,
      createdDate,
      relevanceNorm,
      italyRelevant,
      importanceScore,
    });
  }

  return results;
}

function dedupeByKey(signals: DigestSignal[]): DigestSignal[] {
  const byKey = new Map<string, DigestSignal>();

  for (const signal of signals) {
    const existing = byKey.get(signal.key);
    if (!existing) {
      byKey.set(signal.key, normalizeRelatedFundNames(signal));
      continue;
    }

    const mergedFunds = mergeFundLists(
      existing.relatedFundSlugs,
      existing.relatedFundNames,
      signal.relatedFundSlugs,
      signal.relatedFundNames,
    );
    const keepIncoming =
      signal.importanceScore > existing.importanceScore ||
      (signal.importanceScore === existing.importanceScore && getPrimaryTimestamp(signal) > getPrimaryTimestamp(existing));
    const canonical = keepIncoming ? signal : existing;

    byKey.set(signal.key, normalizeRelatedFundNames({
      ...canonical,
      importanceScore: Math.max(existing.importanceScore, signal.importanceScore),
      relevanceNorm: Math.max(existing.relevanceNorm, signal.relevanceNorm),
      italyRelevant: mergeItalyRelevant(existing.italyRelevant, signal.italyRelevant),
      relatedFundSlugs: mergedFunds.slugs,
      relatedFundNames: mergedFunds.names,
      primaryFundSlug: mergedFunds.slugs.includes(canonical.primaryFundSlug)
        ? canonical.primaryFundSlug
        : mergedFunds.slugs[0] || canonical.primaryFundSlug,
      primaryFundName: mergedFunds.slugs.includes(canonical.primaryFundSlug)
        ? canonical.primaryFundName
        : mergedFunds.names[0] || canonical.primaryFundName,
    }));
  }

  return Array.from(byKey.values());
}

function sortSignalsByImportance(signals: DigestSignal[]): DigestSignal[] {
  return [...signals].sort((a, b) => {
    if (b.importanceScore !== a.importanceScore) {
      return b.importanceScore - a.importanceScore;
    }
    const tDiff = getPrimaryTimestamp(b) - getPrimaryTimestamp(a);
    if (tDiff !== 0) return tDiff;
    return a.key.localeCompare(b.key);
  });
}

function loadSentLog(path: string): SentLog {
  const empty: SentLog = {
    generated_at: new Date(0).toISOString(),
    entries: [],
  };

  const parsed = loadJsonFile<SentLog>(path);
  if (!parsed || !Array.isArray(parsed.entries)) return empty;

  return {
    generated_at: typeof parsed.generated_at === 'string' ? parsed.generated_at : empty.generated_at,
    entries: parsed.entries.filter((entry): entry is SentLogEntry => {
      return (
        typeof entry.signal_key === 'string' &&
        typeof entry.first_sent_at === 'string' &&
        typeof entry.last_sent_at === 'string' &&
        typeof entry.times_sent === 'number' &&
        typeof entry.last_digest_id === 'string'
      );
    }),
  };
}

function updateSentLog(
  sentLog: SentLog,
  selectedSignals: DigestSignal[],
  digestId: string,
  nowIso: string,
): SentLog {
  const byKey = new Map<string, SentLogEntry>();
  for (const entry of sentLog.entries) {
    byKey.set(entry.signal_key, { ...entry });
  }

  for (const signal of selectedSignals) {
    const existing = byKey.get(signal.key);
    if (existing) {
      existing.last_sent_at = nowIso;
      existing.last_digest_id = digestId;
      existing.times_sent += 1;
      byKey.set(signal.key, existing);
    } else {
      byKey.set(signal.key, {
        signal_key: signal.key,
        first_sent_at: nowIso,
        last_sent_at: nowIso,
        times_sent: 1,
        last_digest_id: digestId,
      });
    }
  }

  return {
    generated_at: nowIso,
    entries: Array.from(byKey.values()).sort((a, b) => a.signal_key.localeCompare(b.signal_key)),
  };
}

function rankAndSelectSignals(
  unsentSignals: DigestSignal[],
  fundProfiles: Record<string, FundProfile>,
  maxSignals: number,
  maxPerFund: number,
): DigestSignal[] {
  const byPrimaryFund = new Map<string, DigestSignal[]>();
  for (const signal of sortSignalsByImportance(unsentSignals)) {
    const list = byPrimaryFund.get(signal.primaryFundSlug) ?? [];
    list.push(signal);
    byPrimaryFund.set(signal.primaryFundSlug, list);
  }

  const fundInputs = Array.from(byPrimaryFund.entries()).map(([fundSlug, signals]) => {
    const profile = fundProfiles[fundSlug];
    const fundName = signals[0]?.primaryFundName || profile?.name || prettifyFundSlug(fundSlug);
    const aumEur = profile?.aumEur ?? null;
    const priority = profile?.priorityScore ?? 0;
    const sortedSignals = sortSignalsByImportance(signals);
    const topImportance = sortedSignals[0]?.importanceScore ?? 0;
    const avgRelevance =
      sortedSignals.reduce((sum, signal) => sum + signal.relevanceNorm, 0) / Math.max(sortedSignals.length, 1);

    return {
      fundSlug,
      fundName,
      aumEur,
      priority,
      topImportance,
      avgRelevance,
      signals: sortedSignals,
    };
  });

  const maxLogAum = fundInputs.reduce((max, fund) => {
    if (!fund.aumEur || fund.aumEur <= 0) return max;
    return Math.max(max, Math.log1p(fund.aumEur));
  }, 0);

  const rankedFunds = fundInputs
    .map((fund) => {
      const aumNorm = fund.aumEur && maxLogAum > 0 ? Math.log1p(fund.aumEur) / maxLogAum : 0;
      const fundRankScore =
        fund.topImportance +
        (aumNorm * 40) +
        (fund.avgRelevance * 20) +
        (fund.priority * 0.2);
      return { ...fund, fundRankScore };
    })
    .sort((a, b) => {
      if (b.fundRankScore !== a.fundRankScore) return b.fundRankScore - a.fundRankScore;
      return a.fundName.localeCompare(b.fundName);
    });

  const selected: DigestSignal[] = [];
  const selectedKeys = new Set<string>();
  const selectedPerFund = new Map<string, number>();

  for (const fund of rankedFunds) {
    if (selected.length >= maxSignals) break;
    const current = selectedPerFund.get(fund.fundSlug) ?? 0;
    const remainingForFund = Math.max(0, maxPerFund - current);
    if (remainingForFund <= 0) continue;
    for (const signal of fund.signals) {
      if (selected.length >= maxSignals) break;
      if (selectedKeys.has(signal.key)) continue;
      selected.push(signal);
      selectedKeys.add(signal.key);
      selectedPerFund.set(fund.fundSlug, (selectedPerFund.get(fund.fundSlug) ?? 0) + 1);
      if ((selectedPerFund.get(fund.fundSlug) ?? 0) >= maxPerFund) break;
    }
  }

  if (selected.length < maxSignals) {
    const extras: Array<{ fundRankScore: number; signal: DigestSignal }> = [];
    for (const fund of rankedFunds) {
      for (const signal of fund.signals) {
        if (selectedKeys.has(signal.key)) continue;
        extras.push({ fundRankScore: fund.fundRankScore, signal });
      }
    }
    extras.sort((a, b) => {
      if (b.fundRankScore !== a.fundRankScore) return b.fundRankScore - a.fundRankScore;
      if (b.signal.importanceScore !== a.signal.importanceScore) {
        return b.signal.importanceScore - a.signal.importanceScore;
      }
      return getPrimaryTimestamp(b.signal) - getPrimaryTimestamp(a.signal);
    });
    for (const extra of extras) {
      if (selected.length >= maxSignals) break;
      if (selectedKeys.has(extra.signal.key)) continue;
      selected.push(extra.signal);
      selectedKeys.add(extra.signal.key);
    }
  }

  return sortSignalsByImportance(selected).map(normalizeRelatedFundNames);
}

function countUniqueFunds(signals: DigestSignal[]): number {
  const slugs = new Set<string>();
  for (const signal of signals) {
    for (const slug of signal.relatedFundSlugs) {
      if (!slug) continue;
      slugs.add(slug);
    }
  }
  return slugs.size;
}

function toCsv(emails: string[]): string {
  const lines = ['email'];
  for (const email of emails) {
    if (email.includes(',') || email.includes('"') || email.includes('\n')) {
      lines.push(`"${email.replace(/"/g, '""')}"`);
    } else {
      lines.push(email);
    }
  }
  return `${lines.join('\n')}\n`;
}

function buildDigestText(
  signals: DigestSignal[],
  windowFrom: Date,
  windowTo: Date,
  timezone: string,
): string {
  const lines: string[] = [];
  const includedSignals = signals.length;
  const includedFunds = countUniqueFunds(signals);
  const headerWeek = formatDay(windowTo, timezone);
  const fromLabel = formatDay(windowFrom, timezone);
  const toLabel = formatDay(windowTo, timezone);

  lines.push(`Subject: Fundradar Weekly Signals Digest — Week of ${headerWeek}`);
  lines.push('');
  lines.push('Hi,');
  lines.push('');
  lines.push("Here are this week's PE/VC signals from Fundradar.");
  lines.push('');
  lines.push(`Coverage window (${timezone}): ${fromLabel} to ${toLabel}`);
  lines.push('Date shown: published date when available, otherwise observed date (observed)');
  lines.push(`Funds mentioned: ${includedFunds}`);
  lines.push(`Signals included: ${includedSignals}`);
  lines.push('Ranking: event-first by signal importance and Italy relevance (multi-fund events shown once)');
  lines.push('');

  if (signals.length === 0) {
    lines.push('No new signals matched this window.');
    lines.push('');
  } else {
    for (let i = 0; i < signals.length; i += 1) {
      const signal = signals[i];
      const titleLines = wrapWithIndent(signal.title, `${i + 1}) `, '   ');
      const suffix = `${getDisplayDate(signal, timezone)} — ${toMarkdownLink(getSourceDomain(signal.sourceUrl), signal.sourceUrl)}`;
      const lastIndex = titleLines.length - 1;
      titleLines[lastIndex] = `${titleLines[lastIndex]} — ${suffix}`;
      lines.push(...titleLines);

      const fundsLabel = signal.relatedFundNames.length > 0
        ? signal.relatedFundNames.join(' • ')
        : signal.primaryFundName;
      lines.push(...wrapWithIndent(`Funds: ${fundsLabel}`, '   ', '   '));
      lines.push('');
    }
  }

  const billingPortalUrl =
    process.env.DIGEST_BILLING_PORTAL_URL ||
    process.env.NEXT_PUBLIC_LEGAL_BILLING_PORTAL_URL ||
    'https://billing.stripe.com/p/login/3cIeVcalm8hwfmz6ac57W00';
  const digestUnsubscribeEmail =
    process.env.DIGEST_UNSUBSCRIBE_EMAIL ||
    process.env.NEXT_PUBLIC_LEGAL_DIGEST_UNSUBSCRIBE_EMAIL ||
    process.env.CONTACT_EMAIL ||
    '';

  lines.push(
    `- You are receiving this because your Fundradar subscription is active. Billing cancellation: ${billingPortalUrl}`,
  );
  if (digestUnsubscribeEmail) {
    lines.push(
      `- Digest-only opt-out (without cancelling billing): email ${digestUnsubscribeEmail} with subject "UNSUBSCRIBE".`,
    );
  }

  return `${lines.join('\n')}\n`;
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const now = new Date();
  const windowTo = options.toIso ? parseIsoDateTime(options.toIso, '--to') : now;
  const windowFrom = options.fromIso
    ? parseIsoDateTime(options.fromIso, '--from')
    : new Date(windowTo.getTime() - options.days * 24 * 60 * 60 * 1000);

  if (windowFrom.getTime() >= windowTo.getTime()) {
    throw new Error('Window start must be before window end');
  }

  const projectRoot = resolveProjectRoot();
  const dataDir = join(projectRoot, 'data');
  const derivedDir = join(dataDir, 'derived');
  const digestDir = join(derivedDir, 'digest');
  mkdirSync(digestDir, { recursive: true });

  const fundProfiles = loadFundProfiles(projectRoot);
  const activeRecipients = await loadActiveRecipients();
  const suppressedRecipients = loadSuppressedRecipients(projectRoot);
  const recipients = activeRecipients.filter((email) => !suppressedRecipients.has(email));
  const suppressedCount = activeRecipients.length - recipients.length;

  const loaded = loadSignalsFile(derivedDir);
  const candidates = normalizeCandidates(loaded.signals, windowFrom, windowTo, fundProfiles);
  const deduped = dedupeByKey(candidates);

  const sentLogPath = join(digestDir, 'sent_log.json');
  const sentLog = loadSentLog(sentLogPath);
  const sentKeys = new Set(sentLog.entries.map((entry) => entry.signal_key));

  const unsent = deduped.filter((signal) => {
    if (sentKeys.has(signal.key)) return false;
    // Backward compatibility with historical sent_log entries created with fund-scoped keys.
    for (const slug of signal.relatedFundSlugs) {
      const legacyKey = buildLegacySignalKey({
        sourceUrl: signal.sourceUrl,
        title: signal.title,
        publishedDate: signal.publishedDate,
        fundSlug: slug,
      });
      if (sentKeys.has(legacyKey)) return false;
    }
    return true;
  });
  const selectedSignals = rankAndSelectSignals(unsent, fundProfiles, options.maxSignals, options.maxPerFund);
  const fundsIncluded = countUniqueFunds(selectedSignals);

  const digestText = buildDigestText(selectedSignals, windowFrom, windowTo, options.timezone);
  const recipientsCsv = toCsv(recipients);

  const digestId = `digest-${now.toISOString().replace(/[:.]/g, '-')}`;
  const nowIso = now.toISOString();

  const meta: DigestMeta = {
    digest_id: digestId,
    generated_at: nowIso,
    source_file: loaded.fileName,
    source_file_path: loaded.filePath,
    window_from: windowFrom.toISOString(),
    window_to: windowTo.toISOString(),
    timezone: options.timezone,
    days: options.days,
    max_signals: options.maxSignals,
    max_per_fund: options.maxPerFund,
    ranking_mode: 'event_first_rank_with_primary_fund_diversity_cap_and_multi_fund_projection',
    signals_window_matched: candidates.length,
    signals_after_in_batch_dedupe: deduped.length,
    signals_already_sent: deduped.length - unsent.length,
    signals_included: selectedSignals.length,
    funds_included: fundsIncluded,
    recipients_active: activeRecipients.length,
    recipients_suppressed: suppressedCount,
    recipients_sendable: recipients.length,
    dry_run: options.dryRun,
  };

  const digestTextPath = join(digestDir, 'latest_digest.txt');
  const recipientsPath = join(digestDir, 'latest_recipients.csv');
  const metaPath = join(digestDir, 'latest_digest_meta.json');

  writeFileSync(digestTextPath, digestText);
  writeFileSync(recipientsPath, recipientsCsv);
  writeFileSync(metaPath, JSON.stringify(meta, null, 2));

  if (!options.dryRun) {
    const updatedSentLog = updateSentLog(sentLog, selectedSignals, digestId, nowIso);
    writeFileSync(sentLogPath, JSON.stringify(updatedSentLog, null, 2));
  }

  console.log('Digest build complete.');
  console.log(`  Text digest: ${digestTextPath}`);
  console.log(`  Recipients:  ${recipientsPath}`);
  console.log(`  Meta:        ${metaPath}`);
  console.log(`  Window matched signals: ${candidates.length}`);
  console.log(`  Included signals: ${selectedSignals.length}`);
  console.log(`  Included funds: ${fundsIncluded}`);
  console.log(`  Active recipients: ${activeRecipients.length}`);
  console.log(`  Suppressed recipients: ${suppressedCount}`);
  console.log(`  Sendable recipients: ${recipients.length}`);
  console.log(`  Dry run: ${options.dryRun ? 'yes' : 'no'}`);
}

main().catch((error) => {
  console.error((error as Error).message);
  process.exit(1);
});
