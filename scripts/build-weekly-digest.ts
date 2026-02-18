/**
 * Build weekly digest outputs for Fundradar subscribers.
 *
 * Output files:
 * - latest_digest.txt    (plain text)
 * - latest_recipients.csv
 * - latest_digest_meta.json
 * - sent_log.json        (unless --dry-run)
 *
 * Selection rule:
 * - Compute an effective signal date:
 *   - published_at, if present
 *   - otherwise observed_at
 * - Include only if that effective date is in [window_from, window_to)
 * - Exclude already-sent signals from sent_log.json
 *
 * Ranking:
 * - Funds ranked by AUM + Italy/relevance-weighted signal importance.
 * - Signals within each fund ranked by signals-feed style importance.
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
  fundSlug: string;
  fundName: string;
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

interface FundDigestGroup {
  fundSlug: string;
  fundName: string;
  aumEur: number | null;
  fundRankScore: number;
  signals: DigestSignal[];
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
  dry_run: boolean;
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

    const rawFundSlug = cleanText(raw.fund_slug);
    const fundSlug = toSlug(rawFundSlug || 'unknown-fund') || 'unknown-fund';
    const fundProfile = fundProfiles[fundSlug];
    const fundName = fundProfile?.name || prettifyFundSlug(fundSlug);
    const fundPriority = fundProfile?.priorityScore ?? 0;

    const signalType = cleanText(raw.signal_type) || 'other';
    const id = cleanText(raw.id) || buildSignalKey({ sourceUrl, title, publishedDate: null, fundSlug });

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
      fundSlug,
    });

    results.push({
      id,
      key,
      fundSlug,
      fundName,
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
  const seen = new Set<string>();
  const deduped: DigestSignal[] = [];

  for (const signal of signals) {
    if (seen.has(signal.key)) continue;
    seen.add(signal.key);
    deduped.push(signal);
  }

  return deduped;
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

function rankAndGroupSignals(
  unsentSignals: DigestSignal[],
  fundProfiles: Record<string, FundProfile>,
  maxSignals: number,
  maxPerFund: number,
): FundDigestGroup[] {
  const byFund = new Map<string, DigestSignal[]>();
  for (const signal of sortSignalsByImportance(unsentSignals)) {
    const list = byFund.get(signal.fundSlug) ?? [];
    list.push(signal);
    byFund.set(signal.fundSlug, list);
  }

  const groupInputs = Array.from(byFund.entries()).map(([fundSlug, signals]) => {
    const profile = fundProfiles[fundSlug];
    const fundName = signals[0]?.fundName || profile?.name || prettifyFundSlug(fundSlug);
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
      avgRelevance,
      topImportance,
      signals: sortedSignals,
    };
  });

  const maxLogAum = groupInputs.reduce((max, group) => {
    if (!group.aumEur || group.aumEur <= 0) return max;
    return Math.max(max, Math.log1p(group.aumEur));
  }, 0);

  const rankedGroups = groupInputs
    .map((group) => {
      const aumNorm = group.aumEur && maxLogAum > 0 ? Math.log1p(group.aumEur) / maxLogAum : 0;
      const fundRankScore =
        group.topImportance + // signals-feed style importance (already includes priority)
        (aumNorm * 40) + // AUM weighting
        (group.avgRelevance * 20) + // Italy relevance weighting
        (group.priority * 0.2); // small extra boost from fund priority

      return {
        ...group,
        fundRankScore,
      };
    })
    .sort((a, b) => {
      if (b.fundRankScore !== a.fundRankScore) return b.fundRankScore - a.fundRankScore;
      return a.fundName.localeCompare(b.fundName);
    });

  const selectedGroups: FundDigestGroup[] = [];
  const selectedBySlug = new Map<string, FundDigestGroup>();
  let selectedCount = 0;

  for (const group of rankedGroups) {
    if (selectedCount >= maxSignals) break;
    const takeCount = Math.min(maxPerFund, group.signals.length, maxSignals - selectedCount);
    if (takeCount <= 0) continue;

    const selectedGroup: FundDigestGroup = {
      fundSlug: group.fundSlug,
      fundName: group.fundName,
      aumEur: group.aumEur,
      fundRankScore: group.fundRankScore,
      signals: group.signals.slice(0, takeCount),
    };
    selectedGroups.push(selectedGroup);
    selectedBySlug.set(group.fundSlug, selectedGroup);
    selectedCount += takeCount;
  }

  if (selectedCount < maxSignals) {
    const extras: { fundSlug: string; fundRankScore: number; signal: DigestSignal }[] = [];

    for (const group of rankedGroups) {
      const existing = selectedBySlug.get(group.fundSlug);
      const already = existing ? existing.signals.length : 0;
      for (const signal of group.signals.slice(already)) {
        extras.push({ fundSlug: group.fundSlug, fundRankScore: group.fundRankScore, signal });
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
      if (selectedCount >= maxSignals) break;
      const existing = selectedBySlug.get(extra.fundSlug);
      if (!existing) {
        const profile = fundProfiles[extra.fundSlug];
        const created: FundDigestGroup = {
          fundSlug: extra.fundSlug,
          fundName: extra.signal.fundName || profile?.name || prettifyFundSlug(extra.fundSlug),
          aumEur: profile?.aumEur ?? null,
          fundRankScore: extra.fundRankScore,
          signals: [extra.signal],
        };
        selectedGroups.push(created);
        selectedBySlug.set(extra.fundSlug, created);
      } else {
        existing.signals.push(extra.signal);
      }
      selectedCount += 1;
    }
  }

  selectedGroups.sort((a, b) => {
    if (b.fundRankScore !== a.fundRankScore) return b.fundRankScore - a.fundRankScore;
    return a.fundName.localeCompare(b.fundName);
  });

  for (const group of selectedGroups) {
    group.signals = sortSignalsByImportance(group.signals);
  }

  return selectedGroups;
}

function flattenSignals(groups: FundDigestGroup[]): DigestSignal[] {
  const all: DigestSignal[] = [];
  for (const group of groups) {
    for (const signal of group.signals) {
      all.push(signal);
    }
  }
  return all;
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
  groups: FundDigestGroup[],
  windowFrom: Date,
  windowTo: Date,
  timezone: string,
): string {
  const lines: string[] = [];
  const includedSignals = flattenSignals(groups).length;
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
  lines.push(`Funds included: ${groups.length}`);
  lines.push(`Signals included: ${includedSignals}`);
  lines.push('Ranking: funds ordered by overall signal importance and Italy relevance');
  lines.push('');

  if (groups.length === 0) {
    lines.push('No new signals matched this window.');
    lines.push('');
  } else {
    for (let i = 0; i < groups.length; i += 1) {
      const group = groups[i];
      lines.push(`${i + 1}) ${group.fundName}`);
      for (const signal of group.signals) {
        const titleLines = wrapWithIndent(signal.title, '   - ', '     ');
        const suffix = `${getDisplayDate(signal, timezone)} — ${toMarkdownLink(getSourceDomain(signal.sourceUrl), signal.sourceUrl)}`;
        const lastIndex = titleLines.length - 1;
        titleLines[lastIndex] = `${titleLines[lastIndex]} — ${suffix}`;
        lines.push(...titleLines);
      }
      lines.push('');
    }
  }

  lines.push('- You are receiving this because your Fundradar subscription is active. To manage or cancel your subscription: https://billing.stripe.com/p/login/3cIeVcalm8hwfmz6ac57W00');

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
  const recipients = await loadActiveRecipients();

  const loaded = loadSignalsFile(derivedDir);
  const candidates = normalizeCandidates(loaded.signals, windowFrom, windowTo, fundProfiles);
  const deduped = dedupeByKey(candidates);

  const sentLogPath = join(digestDir, 'sent_log.json');
  const sentLog = loadSentLog(sentLogPath);
  const sentKeys = new Set(sentLog.entries.map((entry) => entry.signal_key));

  const unsent = deduped.filter((signal) => !sentKeys.has(signal.key));
  const selectedGroups = rankAndGroupSignals(unsent, fundProfiles, options.maxSignals, options.maxPerFund);
  const selectedSignals = flattenSignals(selectedGroups);

  const digestText = buildDigestText(selectedGroups, windowFrom, windowTo, options.timezone);
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
    ranking_mode: 'fund_rank = top_signal_importance + size_weight + Italy_relevance_weight',
    signals_window_matched: candidates.length,
    signals_after_in_batch_dedupe: deduped.length,
    signals_already_sent: deduped.length - unsent.length,
    signals_included: selectedSignals.length,
    funds_included: selectedGroups.length,
    recipients_active: recipients.length,
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
  console.log(`  Included funds: ${selectedGroups.length}`);
  console.log(`  Active recipients: ${recipients.length}`);
  console.log(`  Dry run: ${options.dryRun ? 'yes' : 'no'}`);
}

main().catch((error) => {
  console.error((error as Error).message);
  process.exit(1);
});
