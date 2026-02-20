/**
 * Data loading utilities for Fundradar
 *
 * Each data type has a single source of truth in data/derived/:
 *   Funds:      db.json (fund list)
 *   Signals:    detected_signals_filtered.json
 *   Deals:      pem_deals.json
 *   Portfolios: portfolio_items.json
 *   Team:       linkedin/fund_people_stats.json
 *   AIFI data:  aifi_members_enriched.json
 */

import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import type { Fund, Deal, Signal, SignalType, PemManifest, TeamAnalytics, DataSource, Office, Company, CompanyInvestment } from '@fundradar/shared';
import { getRepoRoot } from './repoRoot';
import {
  isGarbageSignal,
  buildKnownFundNames,
  cleanSignalTitle,
  cleanSignalText,
  isRedundantSignalSummary,
  normalizeSignalText,
  reclassifySignalType,
} from './signalProcessing';
import {
  buildFundMentionEntries,
  resolveSignalFundSlugs,
  type FundMentionEntry,
} from './signalFundTags';

interface Database {
  generated_at: string;
  pem_manifest: PemManifest | null;
  funds: Fund[];
}

interface PemDealsFile {
  generated_at: string;
  deals: Deal[];
}

export interface PortfolioCompany {
  fund_slug: string;
  company_id: string;
  company_name: string;
  status: 'current' | 'exited' | 'partial' | null;
  status_source_url?: string | null;
  status_source_label?: string | null;
  entry_date: string | null;
  exit_date: string | null;
  confidence: number;
  // Detail page enrichment fields
  sector?: string | null;
  website?: string | null;
  description?: string | null;
  detail_page_url?: string | null;
  headquarters?: string | null;
  investment_date?: string | null;
  // Data provenance (see DataSource hierarchy in @fundradar/shared)
  data_source?: DataSource;
  // Source citation
  source_url?: string | null;
  source_label?: string | null;
  // PEM-specific fields
  region?: string | null;
  investment_stage?: string | null;
  invested_amount_eur_mln?: number | null;
  deal_year?: number | null;
}

interface PortfoliosFile {
  portfolios: Record<string, PortfolioCompany[]>;
  geoScopes: Record<string, string>;
  sourceUrls: Record<string, string>;
  portfolioNotes: Record<string, string>;
}

/**
 * Manual funds file structure (Gemini-generated data for non-AIFI funds)
 */
interface PemStatusOverride {
  status: 'current' | 'exited' | 'partial' | null;
  source_url?: string | null;
  source_label?: string | null;
  verified_at?: string | null;
}

interface PemStatusOverridesFile {
  generated_at: string;
  overrides: Record<string, Record<string, PemStatusOverride>>;
}

let cachedDb: Database | null = null;
let cachedPemDeals: Deal[] | null = null;
let cachedPemStatusOverrides: PemStatusOverridesFile | null = null;
let cachedAliases: Record<string, string> | null = null;

// getRepoRoot is imported from repoRoot.ts (shared with signals_unified.ts)

function getDbPath(): string {
  return join(getRepoRoot(), 'data', 'db.json');
}

// Derive sector tags from current portfolio companies, ordered by count.
// Reuses loadPortfolios() cache instead of re-reading portfolio_items.json.
let cachedPortfolioSectorTags: Record<string, string[]> | null = null;

function computePortfolioSectorTags(): Record<string, string[]> {
  if (cachedPortfolioSectorTags) return cachedPortfolioSectorTags;

  const portfolios = loadPortfolios();
  const result: Record<string, string[]> = {};

  for (const [slug, companies] of Object.entries(portfolios.portfolios)) {
    const sectorCounts: Record<string, number> = {};
    for (const item of companies) {
      // Include current + null status (single-section pages default to current)
      if (item.status && item.status !== 'current') continue;
      const sector = item.sector;
      if (sector && typeof sector === 'string') {
        sectorCounts[sector] = (sectorCounts[sector] || 0) + 1;
      }
    }
    const sorted = Object.entries(sectorCounts)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([sector]) => sector);
    if (sorted.length > 0) {
      result[slug] = sorted;
    }
  }

  cachedPortfolioSectorTags = result;
  return result;
}

let cachedLinkedInUrls: Record<string, string> | null = null;

function loadLinkedInUrls(): Record<string, string> {
  if (cachedLinkedInUrls) return cachedLinkedInUrls;

  const filePath = join(getRepoRoot(), 'data', 'derived', 'linkedin', 'fund_linkedin_urls.json');
  if (!existsSync(filePath)) {
    cachedLinkedInUrls = {};
    return cachedLinkedInUrls;
  }

  try {
    const data = JSON.parse(readFileSync(filePath, 'utf-8'));
    const map: Record<string, string> = {};
    for (const entry of data.companies || []) {
      if (entry.slug && entry.linkedin_url && !entry.note) {
        map[entry.slug] = entry.linkedin_url;
      }
    }
    cachedLinkedInUrls = map;
  } catch (e) {
    console.error('Failed to load LinkedIn URLs:', e);
    cachedLinkedInUrls = {};
  }

  return cachedLinkedInUrls;
}

function loadAliases(): Record<string, string> {
  if (cachedAliases) return cachedAliases;

  const filePath = join(getRepoRoot(), 'data', 'derived', 'fund_aliases.json');
  if (!existsSync(filePath)) {
    cachedAliases = {};
    return cachedAliases;
  }

  try {
    const data = JSON.parse(readFileSync(filePath, 'utf-8'));
    cachedAliases = (data.aliases as Record<string, string>) || {};
  } catch (e) {
    console.error('Failed to load fund aliases:', e);
    cachedAliases = {};
  }

  return cachedAliases!;
}

export function loadDatabase(): Database {
  if (cachedDb) {
    return cachedDb;
  }

  const dbPath = getDbPath();
  let db: Database;

  if (!existsSync(dbPath)) {
    console.warn('Database not found at', dbPath);
    db = {
      generated_at: new Date().toISOString(),
      pem_manifest: null,
      funds: [],
    };
  } else {
    try {
      const data = readFileSync(dbPath, 'utf-8');
      db = JSON.parse(data);
    } catch (e) {
      console.error('Failed to load database:', e);
      db = {
        generated_at: new Date().toISOString(),
        pem_manifest: null,
        funds: [],
      };
    }
  }

  // Override sector_tags with portfolio-derived sectors (ordered by company count)
  const portfolioSectors = computePortfolioSectorTags();
  for (const fund of db.funds) {
    const derived = portfolioSectors[fund.slug];
    if (derived && derived.length > 0) {
      fund.sector_tags = derived;
    }
  }

  // Merge LinkedIn URLs from separate file
  const linkedinUrls = loadLinkedInUrls();
  for (const fund of db.funds) {
    const url = linkedinUrls[fund.slug];
    if (url) {
      fund.linkedin_url = url;
    }
  }

  cachedDb = db;
  return cachedDb;
}

export function getAllFunds(): Fund[] {
  return loadDatabase().funds;
}

export function getFundBySlug(slug: string): Fund | undefined {
  const funds = loadDatabase().funds;
  const direct = funds.find((f) => f.slug === slug);
  if (direct) return direct;
  // Check aliases for backward-compatible URL support
  const aliases = loadAliases();
  const canonical = aliases[slug];
  if (canonical) return funds.find((f) => f.slug === canonical);
  return undefined;
}

/**
 * Load PEM deals from data/derived/pem_deals.json
 * These are historical deals from PEM PDF reports.
 *
 * IMPORTANT: PEM data references many historical fund names, but db.json only
 * contains the current curated fund universe. Many PEM fund names are defunct, renamed, or not
 * tracked. Do NOT use PEM fund counts to estimate coverage — use db.json only.
 */
function loadPemDeals(): Deal[] {
  if (cachedPemDeals) {
    return cachedPemDeals;
  }

  const pemDealsPath = join(getRepoRoot(), 'data', 'derived', 'pem_deals.json');

  if (!existsSync(pemDealsPath)) {
    console.warn('PEM deals not found at', pemDealsPath);
    return [];
  }

  try {
    const data = readFileSync(pemDealsPath, 'utf-8');
    const file: PemDealsFile = JSON.parse(data);
    cachedPemDeals = file.deals || [];
    return cachedPemDeals;
  } catch (e) {
    console.error('Failed to load PEM deals:', e);
    return [];
  }
}

/**
 * Load PEM status overrides (manual verification of current/exited status).
 * File format: data/derived/pem_status_overrides.json
 */
function loadPemStatusOverrides(): PemStatusOverridesFile {
  if (cachedPemStatusOverrides) {
    return cachedPemStatusOverrides;
  }

  const overridesPath = join(getRepoRoot(), 'data', 'derived', 'pem_status_overrides.json');
  if (!existsSync(overridesPath)) {
    cachedPemStatusOverrides = { generated_at: '', overrides: {} };
    return cachedPemStatusOverrides;
  }

  try {
    const data = readFileSync(overridesPath, 'utf-8');
    cachedPemStatusOverrides = JSON.parse(data);
    return cachedPemStatusOverrides!;
  } catch (e) {
    console.error('Failed to load PEM status overrides:', e);
    cachedPemStatusOverrides = { generated_at: '', overrides: {} };
    return cachedPemStatusOverrides;
  }
}

function getPemStatusOverride(fundSlug: string, dealId: string, normalizedName: string): PemStatusOverride | null {
  const overrides = loadPemStatusOverrides().overrides[fundSlug];
  if (!overrides) return null;
  if (overrides[dealId]) return overrides[dealId];
  if (overrides[normalizedName]) return overrides[normalizedName];
  return null;
}

/**
 * Fix double-character OCR corruption from PEM PDF extraction.
 * Pattern: every character is doubled ("BBuuyy oouutt" → "Buy out").
 * Detects by checking if every pair of adjacent chars matches.
 */
function fixDoubleCharCorruption(text: string | null | undefined): string | null {
  if (!text || text.length < 4) return text ?? null;
  // Check if the string follows the doubled pattern: char pairs must match
  let isDoubled = true;
  for (let i = 0; i < text.length - 1; i += 2) {
    if (text[i].toLowerCase() !== text[i + 1].toLowerCase()) {
      isDoubled = false;
      break;
    }
  }
  if (!isDoubled || text.length % 2 !== 0) return text;
  // Undouble: take every other character
  let fixed = '';
  for (let i = 0; i < text.length; i += 2) {
    fixed += text[i];
  }
  return fixed;
}

export function getDealsForFund(fundSlug: string): Deal[] {
  // Load deals from PEM data and fix OCR corruption in text fields
  return loadPemDeals()
    .filter((d) => d.lead_investor_slug === fundSlug)
    .map(d => ({
      ...d,
      investment_stage: fixDoubleCharCorruption(d.investment_stage) ?? d.investment_stage,
      region: fixDoubleCharCorruption(d.region) ?? d.region,
      sector: fixDoubleCharCorruption(d.sector) ?? d.sector,
      sector_detail: fixDoubleCharCorruption(d.sector_detail) ?? d.sector_detail,
    }));
}

/**
 * Load signals from detected_signals_enriched.json (preferred) or detected_signals_filtered.json.
 * Enriched signals have English translations and AI summaries; filtered has Italian originals.
 */
interface FilteredSignalsFile {
  signals: Signal[];
}

let cachedFilteredSignals: Signal[] | null = null;
let cachedFundMentionEntries: FundMentionEntry[] | null = null;

function loadFilteredSignals(): Signal[] {
  if (cachedFilteredSignals) {
    return cachedFilteredSignals;
  }

  const repoRoot = getRepoRoot();
  const enrichedPath = join(repoRoot, 'data', 'derived', 'detected_signals_enriched.json');
  const filteredPath = join(repoRoot, 'data', 'derived', 'detected_signals_filtered.json');

  // Prefer enriched (has English translations), fall back to filtered
  const pathToUse = existsSync(enrichedPath) ? enrichedPath : filteredPath;

  if (!existsSync(pathToUse)) {
    cachedFilteredSignals = [];
    return cachedFilteredSignals;
  }

  try {
    const data = readFileSync(pathToUse, 'utf-8');
    const file: FilteredSignalsFile = JSON.parse(data);
    cachedFilteredSignals = (file.signals || []).filter(
      (s) => s.signal_type !== 'website_change'
    );
    return cachedFilteredSignals;
  } catch (e) {
    console.error('Failed to load signals:', e);
    cachedFilteredSignals = [];
    return cachedFilteredSignals;
  }
}

export function getSignalsForFund(fundSlug: string): Signal[] {
  if (!cachedFundMentionEntries) {
    const funds = getAllFunds().map((f) => ({ slug: f.slug, name: f.name }));
    cachedFundMentionEntries = buildFundMentionEntries(funds);
  }

  const signals = loadFilteredSignals()
    .map((s) => {
      const related = resolveSignalFundSlugs(
        s as Signal & Record<string, unknown>,
        cachedFundMentionEntries || [],
      );
      return {
        ...s,
        // NOTE: related_fund_names is not populated here (only slugs). Harmless while
        // showFundLink=false on /funds/[slug] signal cards (L4 audit note).
        related_fund_slugs: related.length ? related : (s.fund_slug ? [s.fund_slug] : []),
      } as Signal;
    })
    .filter((s) => (s.related_fund_slugs || []).includes(fundSlug));
  // Build known fund names for misattribution detection (auto-derived from db.json)
  const knownFundNames = buildKnownFundNames(getAllFunds());
  // Deduplicate by content (source_url + title + published_at)
  const seen = new Set<string>();
  const seenContent = new Set<string>();
  return signals
    .filter((s) => {
      const contextSignal = s.fund_slug === fundSlug ? s : { ...s, fund_slug: fundSlug };
      return !isGarbageSignal(contextSignal, knownFundNames);
    })
    .map(s => {
      // Clean title artifacts and reclassify mistyped signals
      const cleanedTitle = cleanSignalText(cleanSignalTitle(s.title || ''));
      const cleanedWhatChanged = cleanSignalText(s.what_changed || '');
      const newType = reclassifySignalType({ ...s, title: cleanedTitle, what_changed: cleanedWhatChanged });
      const isDupText = isRedundantSignalSummary(cleanedTitle, cleanedWhatChanged);
      const finalWhatChanged = isDupText ? '' : cleanedWhatChanged;
      return {
        ...s,
        title: cleanedTitle,
        what_changed: finalWhatChanged,
        ...(newType ? { signal_type: newType } : {}),
      };
    })
    .filter((s) => {
      const key = `${s.source_url}::${s.title}::${s.published_at || ''}`;
      const normTitle = normalizeSignalText(s.title || '');
      const normSummary = normalizeSignalText(s.what_changed || '');
      const contentKey = `${normTitle}::${normSummary || normTitle}::${s.published_at || ''}`;
      if (seen.has(key)) return false;
      if (seenContent.has(contentKey)) return false;
      seen.add(key);
      seenContent.add(contentKey);
      return true;
    });
}

let cachedPortfolios: PortfoliosFile | null = null;

/**
 * Portfolio item structure in portfolio_items.json (unified format)
 */
interface PortfolioItem {
  name: string;
  sector: string | null;
  status: string | null;
  confidence: number;
  website: string | null;
  description: string | null;
  detail_page_url: string | null;
  headquarters: string | null;
  investment_date: string | null;
}

interface PortfolioItemsFile {
  fund_portfolios: Record<string, PortfolioItem[]>;
  fund_source_urls?: Record<string, string>;
  geo_scopes?: Record<string, string>;
  fund_portfolio_notes?: Record<string, string>;
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

/**
 * Load portfolio companies from portfolio_items.json (single source of truth).
 */
function loadPortfolios(): PortfoliosFile {
  if (cachedPortfolios) {
    return cachedPortfolios;
  }

  const result: PortfoliosFile = { portfolios: {}, geoScopes: {}, sourceUrls: {}, portfolioNotes: {} };

  const portfolioPath = join(getRepoRoot(), 'data', 'derived', 'portfolio_items.json');
  if (existsSync(portfolioPath)) {
    try {
      const data = readFileSync(portfolioPath, 'utf-8');
      const file: PortfolioItemsFile = JSON.parse(data);
      const fundPortfolios = file.fund_portfolios || {};
      result.geoScopes = file.geo_scopes || {};
      result.sourceUrls = file.fund_source_urls || {};
      result.portfolioNotes = file.fund_portfolio_notes || {};

      for (const [fundSlug, items] of Object.entries(fundPortfolios)) {
        const companies: PortfolioCompany[] = items
          .map(item => ({ ...item, name: cleanPortfolioName(item.name) }))
          .filter(item => item.name && item.name.length > 2 && (item.confidence ?? 0.7) >= 0.5)
          .filter(item => isValidPortfolioEntry(item.name, fundSlug))
          .map(item => ({
            fund_slug: fundSlug,
            company_id: `temp-${slugify(item.name)}`,
            company_name: item.name,
            status: (item.status as PortfolioCompany['status']) ?? null,
            entry_date: item.investment_date ?? null,
            exit_date: null,
            confidence: item.confidence ?? 0.7,
            sector: item.sector?.replace(/^SECTOR/i, '') || null,
            website: item.website,
            description: item.description,
            detail_page_url: item.detail_page_url,
            headquarters: item.headquarters,
          }));

        // Dedup within fund: keep first occurrence by compact normalized name
        const seen = new Set<string>();
        const deduped = companies.filter(c => {
          const key = compactName(normalizeCompanyName(c.company_name));
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });

        if (deduped.length > 0) {
          result.portfolios[fundSlug] = deduped;
        }
      }
    } catch (e) {
      console.error('Failed to load portfolios:', e);
    }
  }

  cachedPortfolios = result;
  return cachedPortfolios;
}

/**
 * Get a mapping of fund slug -> portfolio company names (lowercased) for search.
 * Includes both website portfolio and PEM deal targets.
 */
export function getAllPortfolioCompanyNames(): Record<string, string[]> {
  const portfolios = loadPortfolios();
  const pemDeals = loadPemDeals();
  const result: Record<string, string[]> = {};

  // Website portfolio names
  for (const [slug, companies] of Object.entries(portfolios.portfolios)) {
    result[slug] = companies
      .map(c => c.company_name.toLowerCase())
      .filter(name => name.length > 0);
  }

  // PEM deal target names (add to existing or create new entry)
  for (const deal of pemDeals) {
    const slug = deal.lead_investor_slug;
    const name = normalizeViaMarker(deal.target_company).toLowerCase();
    if (name.length <= 2) continue;
    if (!result[slug]) result[slug] = [];
    if (!result[slug].includes(name)) {
      result[slug].push(name);
    }
  }

  return result;
}

/**
 * Normalize a company name for fuzzy matching between data sources.
 * Strips common Italian corporate suffixes and normalizes whitespace.
 */
/**
 * Reject garbage portfolio entries: nav text, article titles, error pages, fund names.
 * Returns true if the entry looks like a real company name.
 */
function isValidPortfolioEntry(name: string, fundSlug: string): boolean {
  const trimmed = name.trim();
  if (!trimmed || trimmed.length <= 2) return false;

  // Reject names longer than 60 chars (article titles, error messages, image alt text)
  if (trimmed.length > 60) return false;

  // Reject if name starts with "Logo " (scraped nav logos)
  if (/^Logo\s/i.test(trimmed)) return false;

  // Reject colon-subtitle patterns where the part after the colon is long
  // (article titles like "CCC: the road to innovation")
  // But allow short colon usage like "MED:ON"
  const colonMatch = trimmed.match(/:\s*(.+)/);
  if (colonMatch && colonMatch[1].length > 10) return false;

  // Reject long parenthetical descriptions: "PRI (Principles for Responsible Investment)"
  // Real company names with parentheticals are short: "3M (Italy)" OK
  const parenMatch = trimmed.match(/\(([^)]+)\)/);
  if (parenMatch && parenMatch[1].length > 20) return false;

  // Reject names that end with a colon (filter labels like "REGIONS:", "INDUSTRY:")
  if (/^[A-Z]+:$/.test(trimmed)) return false;

  // Reject article-title patterns: gerund + lowercase word(s) + preposition
  // "Banking on software" ✗ | "Making investing simpler with X" ✗ | "Bending Spoons" ✓
  if (/^[A-Z][a-z]+ing\s+(?:on|in|into|with|for|new|big|the|a|an)\s/i.test(trimmed)) return false;
  if (/^[A-Z][a-z]+ing\s+\w+\s+\w*\s*(?:with|for|in|into)\s/i.test(trimmed)) return false;

  // Reject description-like text ("Leading provider of...", "A leading...", "One of the...", "Global leader in...")
  if (/^(?:A\s+)?leading\s+/i.test(trimmed)) return false;
  if (/^(?:Global|World|European|Italian?)\s+leader\s+/i.test(trimmed)) return false;
  if (/^One of the\s+/i.test(trimmed)) return false;
  // Reject description sentences (contains "is a", "is the", "is one of" — company descriptions, not names)
  if (/\bis (?:a|the|one of)\b/i.test(trimmed)) return false;

  // Reject Italian investment-category headings
  if (/^Investimenti\s/i.test(trimmed)) return false;

  // Reject sector/industry category names (exact match, case-insensitive)
  const SECTOR_NAMES = new Set([
    'consumer & leisure', 'consumer', 'consumer goods', 'consumer products',
    'industrials & energy transition', 'industrials', 'industrial',
    'tmt', 'technology', 'tech', 'digital',
    'business services', 'services', 'professional services',
    'healthcare', 'health', 'life sciences',
    'financial services', 'finance', 'financials',
    'energy', 'energy transition', 'renewables',
    'infrastructure', 'infra',
    'media & telecom', 'telecom', 'telecommunications', 'media',
    'real estate', 'property',
    'education', 'food & beverage',
    'private equity', 'venture capital',
    'esg', 'impact investing',
    'pri', 'unpri',
    'other',
    'credit', 'equity', 'real assets',
  ]);
  if (SECTOR_NAMES.has(trimmed.toLowerCase())) return false;

  // Reject concatenated words >15 chars containing portfolio/company substrings
  // Catches "Ourportfoliocompanies", "Investmentportfolio", etc.
  if (!/\s/.test(trimmed) && trimmed.length > 15) {
    const lower = trimmed.toLowerCase();
    if (/portfolio|company|companies|investment|ourport/.test(lower)) return false;
  }

  // Reject known UI/nav patterns (case-insensitive)
  const NAV_PATTERNS = [
    /^page not found/i,
    /^click here/i,
    /^powered by/i,
    /vai alla/i,
    /^stay tuned/i,
    /^logout$/i,
    /^portfolio stories/i,
    /^what we do$/i,
    /^about us$/i,
    /^contact us$/i,
    /^home$/i,
    /^menu$/i,
    /^search$/i,
    /^clear$/i,
    /^privacy policy/i,
    /^cookie policy/i,
    /^infrastrutture:$/i,
    /notizie\s*leggi/i,
    /publications.*report/i,
    /combined\s*shape/i,
    /\.pdf$/i,
    /^work with us$/i,
    /^case stud(?:y|ies)$/i,
    /^awards$/i,
    /^governance$/i,
    /^sustainability$/i,
    /^compliance$/i,
    /^ombudsman$/i,
    /^people$/i,
    /^employees$/i,
    /^error page/i,
    /^cross.border\s+merger/i,
    /with\s+clouds?$/i,
    /\bmerger\s+on\s+\d/i,
    // Filter/section UI elements
    /^share this page$/i,
    /^back to top$/i,
    /^portfolio$/i,
    /^current portfolio$/i,
    /^prior investments$/i,
    /^investments?$/i,
    /^our (?:activities|latest news|investments|portfolio)$/i,
    /^funds under management$/i,
    // PAI Partners stat headings from generic strategies
    /^core\s+sectors$/i,
    /^employees\s+across\s+portfolio$/i,
    /^countries\s+with\b/i,
    /^years?\s+average\s+holding/i,
    /^(?:all )?(?:sectors?|industries|strateg(?:y|ies)|regions?|status|year)$/i,
    /^informativa$/i,
    /^name:?$/i,
    // Image alt text (long descriptive phrases, not short company names)
    /^(?:abstract|digitally)\s/i,
    /^(?:man|woman|young|person)\s+\w+\s+\w+\s/i,
    /\b(?:looking|sitting|standing|hugging|hiking)\b/i,
    /\b(?:background|pie chart|bar graph|generated image)\b/i,
    // Italian UI / error pages / nav
    /^la pagina richiesta/i,
    /^per chi vuole/i,
    /^per le\s+(imprese|pubbliche)/i,
    /^chi siamo/i,
    /^who we are$/i,
    /^scopri di più$/i,
    /^news e media/i,
    /you may want to visit/i,
    /^la prospettiva di\b/i,
    /magazine\s+digitale\b/i,
    /\bprivacy by\b/i,
    /\bconsiglio di amministrazione\b/i,
    // Tagline / slogan patterns
    /^delivering\s+\w+\s+\w+\s+with\s+/i,
    // News headlines as company names (contains verbs like "chiude", "closes", "enters")
    /\b(?:chiude|closes?|enters?)\s+(?:un|a|the|il|lo|la)\s/i,
    // SVG element names extracted as company names (Path 40466, Group 5342)
    /^(?:path|group|rect(?:angle)?|circle|line|polygon|ellipse|use|mask|clippath|defs)\s+\d+$/i,
    // Note: trailing " logo" is stripped by cleanPortfolioName() before validation,
    // so "CEME logo" → "CEME" (kept), while "Logo X" is caught by ^Logo\s above.
    // Cookie/tracking (igi-private-equity, oltre-impact-sgr, kkr — 10+ entries)
    /^cookielawinfo-/i,
    /^viewed_cookie/i,
    /^cookie notice$/i,
    /cookies?$/i, // "Performance Cookies", "Targeting Cookies", etc.
    /^strictly necessary/i,
    /^functional cookies?/i,
    /^analytics cookies?/i,
    /^you appear to be located/i, // Geolocation notices
    /^we are currently targeting/i, // L Catterton section header
    // Social media icon names (gepafin, prana-ventures — 3 entries)
    /^(?:facebook|linkedin|twitter|instagram|youtube)-[a-z]+$/i,
    // Navigation UI (axon-partners, capza, equita-capital, simest, zenit — 8 entries)
    /^our companies$/i,
    /^back to homepage$/i,
    /^homepage$/i,
    /torna alla homepage/i,
    // Menu labels (invitalia — 5 entries)
    /\s-\s+menu\s+/i,
    // Image filenames with pixel dimensions (gradiente-sgr, oxy-capital — 2 entries)
    /\d{2,4}x\d{2,4}/,
    // CSS artifacts and trailing punctuation (apollo, gradiente — 5 entries)
    /^[a-z]+-[a-z]+-$/,
    /^[a-z]+-$/,
    /_$/,
    // Italian "Portafoglio" (clessidra-sgr — 1 entry)
    /^portafoglio$/i,
    // Portal branding (simest — 2 entries)
    /^portale\s+/i,
    // Equipment category names
    /^scafalatura\s/i,
    // Italian "Investimenti" headings/labels (f2i-sgr, green-arrow, fsi — "Investimenti 2", "Investimenti diretti", etc.)
    /^investimenti\b/i,
    // Italian "Contatti" / "CONTATTI" (alternative-capital, excellis, narval, sinloc, siryo)
    /^contatti$/i,
    // Language selectors (siryo, tages-capital — "Italiano", "English")
    /^(?:english|italiano|français|deutsch|español)$/i,
    // Pagination buttons (bain-capital — "Next")
    /^(?:next|prev|previous)$/i,
    // Italian section headers (b4-investimenti — "Il Gruppo", "Il nostro team", "Il Club B4")
    /^il\s+(?:gruppo|club|nostro|team)\b/i,
    // Italian section headers (mediocredito — "La Sezione speciale")
    /^la\s+sezione\b/i,
    // Login/auth form text (arca-space-capital — "Login|Forgot Your Password?")
    /^login\b/i,
    // what3words addresses (key-capital — "///estinta.calati.cubi")
    /^\/\/\//,
    // Stock photo alt text: descriptions starting with action/adjective + noun
    /^(?:photograph|photo|image|picture)\s+of\b/i,
    /^(?:father|mother|three|two|smiling|happy)\s+\w+\s+\w+\s+\w+/i,
    /\b(?:sat|hug|hugging|emerging|smiling|chemist|laboratory|wheelchair|laptops?|notebooks?)\b/i,
    // News headlines with currency amounts ("closes CHF 2.1M", "raises EUR 50M")
    /\b(?:closes?|raises?|secures?)\s+(?:CHF|EUR|USD|GBP|£|\$|€)\s*[\d.,]+/i,
    // Section headings extracted as company names (ambienta — "Primary acquisitions")
    /^primary\s+(?:acquisitions|investments)/i,
    /^(?:recent|past|current|former|selected)\s+(?:acquisitions|investments|deals)/i,
    // Fund vehicle names mistaken for companies ("Alto Capital V", "Fondo Basket Eque")
    /\b(?:fund|fondo|capital)\s+[IVX]+$/i,
    /^fondo\s+(?:basket|chiuso|aperto)\b/i,
    // NAV/UI text: "View company website", "Read more", "Download PDF"
    /^view\s+(?:company\s+)?website$/i,
    /^(?:read|learn|find out)\s+more$/i,
    /^download\b/i,
    // Form/UI placeholder text (any language)
    /^lascia\s+un\s+commento/i,
    /^leave\s+a\s+(?:comment|reply)/i,
    // Broadened stock photo alt text: common object descriptions (not company names)
    /^(?:fibre|cable|yellow|green|blue|red|white|black)\s+\w+s?$/i,
    /^teenager\s/i,
    // Photo/image descriptions with typo tolerance (e.g. "Photograaph")
    /^photogra\w+\s+of\b/i,
    // Sports/event names (not companies) — catches domain collisions
    /\b(?:campionato|torneo|olimpiad[ei]|coppa|trofeo|gara)\b/i,
    /\bsquadra\s+(?:nazionale|regionale)\b/i,
    // Generic slogans/taglines extracted as company names
    // (motivational phrases >5 words without deal/company-related keywords)
    /^(?:success|together|delivering|building|creating|making\s+the\s+world)\s+\w+\s+\w+\s+\w+/i,
    // Short slogans/taglines (3 words: "Empowered to succeed", "Built to last")
    /^(?:empowered|built|designed|driven|committed)\s+to\s+\w+$/i,
    // Article titles / questions (never company names)
    /\?\s*$/,
    // Year + report/perspective terms ("2026 Investment Perspectives")
    /^\d{4}\s+(?:investment|annual|quarterly|market|economic|outlook|perspectives?|report)/i,

    // Image file extensions (Ardian logo grid artifacts)
    /\.(jpg|jpeg|png|gif|svg|webp)$/i,

    // Italian navigation (FSI, other Italian funds)
    /^come operiamo$/i,
    /^comunicati stampa$/i,
    /^il fondo$/i,
    /^sostenibilit[aà]$/i,
    /^linee guida/i,
    /^esg\s+per\b/i,
    /^video$/i,
    /^it\s+it$/i,
    /^iniziative$/i,
    /^persone$/i,
    /^impact\s+report$/i,
    /^governance$/i,
    /^media$/i,

    // Stats/label text (PAI Partners, similar)
    /at a glance$/i,
    /^offices?\s+worldwide$/i,
    /^assets?\s+under\s+management$/i,
    /^full.time\s+employees$/i,
    /^capital\s+raised$/i,
    /^\w+\s+buyout\s+fund$/i,
    /^featured\s+content$/i,

    // Business category names (Apollo)
    /^asset\s+management$/i,
    /^retirement\s+solutions$/i,
    /^capital\s+solutions$/i,
    /^real\s+assets$/i,

    // UUID/hash patterns (FSI GUIDs)
    /^[0-9a-f]{8}[\s-][0-9a-f]{4}/i,

    // CSS class/icon artifacts (Oakley)
    /close-icon/i,

    // Single generic navigation words (Zest Group, others)
    /^news$/i,
    /^innovation$/i,
    /^content\s+hub$/i,
    /^the\s*hub$/i,

    // 3D render / stock image alt text (Zest Group)
    /^3d\s+render\b/i,
    /^foto\s+sito\b/i,
    /\bheader\s+investments?$/i,

    // Italian section headers (Alternative Capital Partners, other Italian funds)
    /^i nostri valori$/i,
    /^le nostre storie$/i,
    /^dove investiamo$/i,
    // Italian section headers from fund requirement/criteria pages (Sviluppo Imprese Centro Italia, etc.)
    /^esigenz[ei]\b/i,
    /^requisiti\b/i,
    /^criteri\b/i,
    /^caratteristiche\b/i,
    /^tipologi[ae]\b/i,
    /^settori?\s+di\b/i,
    /^informazion[ie]\b/i,
    /^mission[ei]?\b/i,
    /^strategi[ae]\b/i,
    /^modalit[aà]\b/i,
    /^interventi?\b/i,
    /^strumenti?\s+di\b/i,
    /^il\s+processo\b/i,
    /^le\s+fasi\b/i,
    /^ambiti?\s+di\b/i,

    // Fund product names (not portfolio companies)
    // Note: \bfund$/i was too aggressive — rejects real sub-funds like "Indaco BIO Fund"
    // Use specific patterns instead: "X buyout fund" (line ~1041), "Fund III" (line ~994)
    /^sustainable\s+securities/i,
    /^smes?\s+alternative\s+credit/i,
    /\b(?:senior\s+)?loan\s+fund$/i,

    // Generic nav words
    /^key\s+numbers$/i,
    /^dna\s+/i,

    // Fund investment attribution text (Fondo Italiano generic strategy artifacts)
    /\binvestimento\s+diretto\b/i,

    // Fund-of-Funds entries (CDP Equity FoF vehicles, not portfolio companies)
    /^FoF\s/i,
    /^fund.of.funds?\b/i,
    // French fund portfolio names (Abenex real estate fund vehicles)
    /^portefeuille\s/i,
    // Real estate property names (Abenex: "Residential Complex Rue Campagne...")
    /^residential\s+(?:complex|building|property|tower)/i,
    /^commercial\s+(?:complex|building|property)/i,
    // French street addresses ("12 Rue de la Paix", "Avenue des Champs-Élysées")
    /^\d+\s+(?:rue|avenue|boulevard|place|impasse|passage|allée)\b/i,
    /^(?:rue|avenue|boulevard|place|impasse|passage|allée)\s+/i,

    // Italian HR/legal pages (Siryo, others)
    /^lavora\s+con\s+noi$/i,
    /^eventi$/i,
    /^informativa\b/i,
    /^uploads$/i,
    // Section headers like "Overview Energy", "Overview Infrastructure" (eqt)
    /^overview\s+\w+/i,
    /^investimenti\s+portfolio$/i,

    // SVG/CSS icon names (Entangled Capital)
    /^icon$/i,
    /^arrow$/i,

    // Image placeholder with number (Oakley "Phenna Image 2")
    /\bimage\s+\d/i,
    // Broken image placeholders (Perwyn generic strategy: "image-broken")
    /^image[-\s]broken$/i,

    // Logo references mid-name (F2i generic strategy: "fhp logo new (2)", "LOGO GESAC NEW")
    /\blogo\b/i,

    // Italian marketing headings (Nextalia generic strategy: "MISSION", "VISION")
    /^mission$/i,
    /^vision$/i,
    /^network\s+e\s+opportunit/i,
    /^posizionamento\s+unico$/i,
    /^strategi[ae]\b/i,

    // Person names extracted from team pages as portfolio (Zenit generic strategy)
    /^curriculum$/i,
    /^advisory\s+board$/i,

    // Image alt text patterns (F2i generic strategy: "Immagine1", "SWDES")
    /^immagine\d/i,
    /^swdes$/i,

    // Ultra-short navigation words (B4 Investimenti: "What", "Who", "How")
    /^(?:what|who|how|why|when|where)$/i,
    // Italian corporate governance page names (B4, others)
    /^organi\s+societ/i,
    // Zest Group news headlines leaking into portfolio
    /\bchiude\s+un\s+round\b/i,
    /\bcloses?\s+(?:a\s+)?(?:CHF|EUR|USD|GBP|[€$£])\b/i,
    /\bpre-seed\s+(?:funding\s+)?round\b/i,

    // Italian corporate instruction text (sviluppo-imprese-centro-italia-sgr)
    /\bimpresa\s+target\b/i,
    /\bcaratteristiche\s+tipiche\b/i,
    /\bvantaggi\s+per\b/i,
    /\besigenze\s+dell/i,

    // Section headers ending with colon (equiter: "Rigenerazione Urbana:", "Piccole e Medie Imprese:")
    /^[\w\s]{5,}:$/,

    // News article titles with "Successful/Completion/Realisation" (DBAG)
    /^successful\s+\w+\s+of\b/i,
    /\brealisation\s+of\s+investment\b/i,

    // Generic page section headings (CVC DIF generic strategy)
    /^introduction$/i,
    /^filter\s+results$/i,

    // FSI/Italian fund about-page headings
    /\bmembro\s+della\b/i,
    /^sostenibilit\w+\s+nei\b/i,

    // BU Partners / Eureka section headings
    /^active\s+investments?$/i,
    /^realized\s+investments?$/i,
    /^active\s+label$/i,

    // Fund names, strategy pages, section headers
    /^fondo\s+/i,
    /^strategie\b/i,
    /^eventi$/i,
    /^informativa\b/i,
    /^whistleblowing$/i,
    /:\s*$/,  // Section headers ending with colon
    /^realizzate\s+fondo\b/i,
    /^team\s+\w+$/i,
    /^(?:esigenze|caratteristiche|vantaggi)\b/i,
    /^fund.of.funds\s+model$/i,
    /^investimenti\s+in\s+equity$/i,

    // Deal signal fragments (Italian/English stake descriptions, not company names)
    // Italian: "una quota di ... maggioranza in X", "il 100% di X", "il controllo di X"
    /^(?:una?\s+)?(?:quota|partecipazione)\s+(?:di\s+)?(?:ampia\s+|significativa\s+)?(?:maggioranza|minoranza)\s+/i,
    /^(?:il|lo|la|un|una)\s+[\d.,]+%\s+(?:di|del|della|dell')\s+/i,
    /^(?:il|la)\s+(?:controllo|maggioranza)\s+(?:di|del|della|dell')\s+/i,
    // English: "a majority stake in X", "a minority interest in X"
    /^(?:a\s+)?(?:majority|minority|significant|controlling|strategic|additional)\s+(?:stake|interest|position|holding)\s+in\s+/i,
    // Fund vehicle / co-investment vehicle names (CDP Venture Capital)
    /\bSICAF\b/i,
    /\bEuVECA\b/i,
    // Stat headings (Sinloc: "350+ Mln€ capex generati", "Circa 1,4 Mld€", "130 investimenti")
    /^\d+\+?\s*(?:Mln|Mld|M|B)[\s€$£]/i,
    /^circa\s+\d/i,
    /^\d+\s+investimenti$/i,
    // Section heading "Settori Di Intervento"
    /^settori\s+di\s+intervento$/i,
    /^fondi$/i,

    // Italian ALL CAPS impact/theme categories (SEFEA Impact, other impact funds)
    /^PRODUZIONE E CONSUMO/,
    /^SALUTE E BENESSERE$/,
    /^PROMOZIONE SOCIALE/,
    /^HOUSING SOCIALE$/,
    /^INCLUSIONE EDUCATIVA/,
    /^MOBILIT[AÀ] SOSTENIBILE$/,
    /^PRODUZIONE ENERGIE/,
    /^RICONVERSIONE ENERGETICA$/,
    /^TURISMO SOSTENIBILE$/,
    /^TUTELA DELLA BIODIVERSIT/,
    // Generic ALL CAPS 2+ word Italian phrases that are likely categories (safety net)
    /^[A-ZÀÈÉÌÒÙ]{3,}\s+(?:E\s+)?[A-ZÀÈÉÌÒÙ]{3,}(?:\s+[A-ZÀÈÉÌÒÙ]{3,})*$/,
    // "Società partecipate" section header
    /^societ[aà]\s+partecipate$/i,
    // Fund strategy/product names (Sienna, other asset managers)
    /^(?:european\s+)?(?:high\s+yield|leveraged\s+loan)$/i,
    /^private\s+debt$/i,
    /^special\s+sit(?:uation)?s?$/i,
    /^transition\s+energy$/i,
    /^collocators?$/i,
    /\bELTIF\b/,
    // Government programs mistaken for companies
    /^nuova\s+sabatini$/i,
    // Duplicate-suffix patterns: entries ending with " 2", " 3" etc.
    // (generic strategies produce "Company 2", "Company 3" duplicates)
    /\s+[23456789]$/,
    // FKA/AKA parenthetical aliases (Bain: "Advantage Solutions (FKA Daymon Worldwide)")
    /\((?:fka|aka|formerly|previously)\s+[^)]+\)$/i,
  ];
  for (const pattern of NAV_PATTERNS) {
    if (pattern.test(trimmed)) return false;
  }

  // Reject duplicate-word entries like "Assio Assio" (Ibla Capital scrape artifact)
  const words = trimmed.split(/\s+/);
  if (words.length === 2 && words[0].toLowerCase() === words[1].toLowerCase()) return false;

  // Reject if name matches the fund's own name or is a variant of it
  const fundNameFromSlug = fundSlug.replace(/-/g, ' ').toLowerCase();
  const nameNormalized = trimmed.toLowerCase().replace(/[^a-z0-9\s]/g, '').trim();
  if (nameNormalized === fundNameFromSlug) return false;
  // Also check concatenated (no-space) match: "PranaVentures" → "pranaventures" = "prana ventures" compacted
  const nameCompact = nameNormalized.replace(/\s/g, '');
  const fundCompact = fundNameFromSlug.replace(/\s/g, '');
  if (nameCompact === fundCompact) return false;

  // Strip common fund suffixes to get core name for comparison
  const FUND_SUFFIXES = /\b(sgr|s\.?g\.?r\.?|capital|partners|investimenti|advisory|management|group|holding|fund|alternative funds|real estate)\b/gi;
  const fundCoreName = fundNameFromSlug.replace(FUND_SUFFIXES, '').replace(/\s+/g, ' ').trim();
  const entryCoreName = nameNormalized.replace(FUND_SUFFIXES, '').replace(/\s+/g, ' ').trim();

  // Reject if core names match (e.g. "DeA Capital" vs "dea-capital-alternative-funds-sgr")
  // Use >= 2 for exact match (safe: "b4" === "b4"), >= 3 for prefix checks below
  if (fundCoreName.length >= 2 && entryCoreName === fundCoreName) return false;

  // Reject if entry core starts with fund core as a whole word (not mid-word)
  // "Star III" rejected for fund "star-capital-sgr" (core "star")
  // "Starbucks" NOT rejected (no word boundary after "star")
  if (fundCoreName.length >= 3 && entryCoreName.length > fundCoreName.length) {
    const afterFundCore = entryCoreName.slice(fundCoreName.length);
    if (entryCoreName.startsWith(fundCoreName) && (afterFundCore[0] === ' ' || /^\d/.test(afterFundCore))) return false;
  }
  if (fundCoreName.length > entryCoreName.length && entryCoreName.length >= 3) {
    const afterEntryCore = fundCoreName.slice(entryCoreName.length);
    if (fundCoreName.startsWith(entryCoreName) && (afterEntryCore[0] === ' ' || /^\d/.test(afterEntryCore))) return false;
  }

  // Reject partial fund name + generic suffix ("Advent Investment", "Apollo Capital Management")
  const fundWords = fundNameFromSlug.split(/\s+/);
  if (fundWords.length > 0 && fundWords[0].length >= 3) {
    const firstWord = fundWords[0];
    if (nameNormalized.startsWith(firstWord) && nameNormalized.length > firstWord.length) {
      const rest = nameNormalized.slice(firstWord.length).trim();
      if (/^(investment|capital|partners|management|im |group|advisory|sgr|holding|fund|real estate|alternative)/i.test(rest)) return false;
    }
  }

  // Reject "Gruppo [FundName]" (e.g. "Gruppo Mittel" for mittel)
  if (/^gruppo\s+/i.test(trimmed)) {
    const afterGruppo = trimmed.replace(/^gruppo\s+/i, '').toLowerCase().replace(/[^a-z0-9\s]/g, '').trim();
    if (fundCoreName.length >= 3 && afterGruppo.includes(fundCoreName)) return false;
  }

  // Reject "[FundWord] Asset Management/SGR/Holding" self-references
  // e.g. "Sella SGR" for banca-sella-holding
  const SELF_REF_SUFFIXES = /\s+(?:asset\s+management|sgr|holding|venture\s+partners|circle)\s*(?:s\.?p\.?a\.?)?$/i;
  if (SELF_REF_SUFFIXES.test(trimmed) && fundWords[0]?.length >= 3) {
    const beforeSuffix = trimmed.replace(SELF_REF_SUFFIXES, '').toLowerCase().replace(/[^a-z0-9\s]/g, '').trim();
    if (fundCoreName.includes(beforeSuffix) || beforeSuffix.includes(fundCoreName)) return false;
  }

  return true;
}

function stripPromotionalSuffix(name: string): string {
  return name
    .replace(/\s*\|\s*(?:Invested by|Formerly)\s+.+$/i, '')
    .replace(/\s*\|\s*\w+\s+SGR\b.*$/i, '')
    .replace(/\s*\|\s*\w+\s+subsidiary\b.*$/i, '')
    .trim();
}

function normalizeViaMarker(name: string): string {
  // Keep acquisition marker "via" lowercase in parentheticals.
  // Example: "Centauto (Via FL Selenia)" -> "Centauto (via FL Selenia)"
  let normalized = name.replace(/\(\s*Via(?=\s+)/g, '(via');
  // Defensive: if the whole name starts with "Via " and also contains "(via ...)",
  // treat the leading token as the same marker (not a street prefix).
  if (/^Via\s+/i.test(normalized) && /\(\s*via\s+/i.test(normalized)) {
    normalized = normalized.replace(/^Via(?=\s+)/i, 'via');
  }
  return normalized;
}

/**
 * Clean a raw portfolio company name before validation.
 * Strips common scraping artifacts so real companies aren't rejected.
 * Applied BEFORE isValidPortfolioEntry() runs.
 */
function cleanPortfolioName(name: string): string {
  let cleaned = normalizeViaMarker(name.trim());
  // Strip trailing " logo" from image alt text (muzinich-co has 122 of these)
  cleaned = cleaned.replace(/\s+logo$/i, '');
  // Strip promotional suffixes ("| Invested by...", "| Vertis SGR SpA")
  cleaned = stripPromotionalSuffix(cleaned);
  // Strip leading/trailing pipe characters left from incomplete stripping
  cleaned = cleaned.replace(/^\s*\|\s*/, '').replace(/\s*\|\s*$/, '');
  // If pipe still remains (e.g. "LEN Medical | Axis Santé"), keep text before pipe
  if (cleaned.includes('|')) {
    const beforePipe = cleaned.split('|')[0].trim();
    if (beforePipe.length >= 3) cleaned = beforePipe;
  }
  // Strip trailing period from sentence-like entries (clean up for validation)
  cleaned = cleaned.replace(/\.\s*$/, '');
  // Strip trailing underscores from image alt text artifacts (gradiente-sgr: "Bamboom_", "Hawai_")
  // Note: trailing hyphens ("close-") are kept and caught by NAV_PATTERN instead,
  // since stripping them could create false positives ("close" is not a company)
  cleaned = cleaned.replace(/_+$/, '');
  return cleaned.trim();
}

function normalizeCompanyName(name: string): string {
  return stripPromotionalSuffix(normalizeViaMarker(name))
    .toLowerCase()
    .replace(/\s*\(.*\)/, '')        // Strip parenthetical content: "(via X)", "(Via X)", "(fka Y)", etc.
    .replace(/\s+logo$/, '')         // Strip trailing "logo" from image alt text
    .replace(/\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|s\.?n\.?c\.?|s\.?s\.?|ltd\.?|llc\.?|inc\.?|gmbh\.?|ag\.?|b\.?v\.?|n\.?v\.?|plc\.?|corp\.?|corporation|company|holding|holdings)\b/g, '')
    .replace(/\s+group$/i, '')       // Strip trailing "Group" — "Nactarome Group" → "Nactarome"
    .replace(/\s+technologies$/i, '') // Strip trailing "Technologies" — "Lakesight Technologies" → "Lakesight"
    .replace(/[^a-z0-9]/g, ' ')      // Non-alphanumeric → space (handles hyphens: "SF-Filter" → "sf filter")
    .replace(/\s+/g, ' ')
    .trim();
}

function compactName(normalized: string): string {
  return normalized.replace(/\s/g, '');
}

const PEM_BASE_URL = 'https://www.liucbs.it/osservatori/private-equity-monitor-pem/';


export function getPortfolioForFund(fundSlug: string): PortfolioCompany[] {
  const portfolios = loadPortfolios();
  const portfolioSourceUrls = loadPortfolios().sourceUrls;
  const websiteSourceUrl = portfolioSourceUrls[fundSlug] || null;

  const rawWebsiteCompanies = portfolios.portfolios[fundSlug] || [];

  // Companies on a fund's portfolio page are current investments by definition.
  // Only keep explicit status when the extractor distinguishes current vs exited;
  // otherwise default to "current" since they came from the live portfolio page.
  // Preserve data_source and source_url from the entry itself (set by scraper),
  // falling back to fund-level source URL for legacy data.
  const websiteCompanies = rawWebsiteCompanies.map(c => {
    const dataSource = (c as any).data_source || 'fund_website';
    const isManual = dataSource === 'manual';
    const isSignal = typeof dataSource === 'string' && dataSource.startsWith('signal_');
    // Use entry-level source_url if available, otherwise fall back to fund-level
    const entrySourceUrl = (c as any).source_url || null;
    const effectiveSourceUrl = isManual ? null : (entrySourceUrl || (isSignal ? null : websiteSourceUrl));
    // Source label: signal-derived entries show "Signal" with provenance detail
    let sourceLabel: string;
    if (isManual) {
      sourceLabel = 'Manual';
    } else if (isSignal) {
      sourceLabel = dataSource === 'signal_fund_press' ? 'Press Release'
        : dataSource === 'signal_rumor' ? 'Rumor'
        : 'Signal';
    } else {
      sourceLabel = effectiveSourceUrl ? 'Website' : 'Unknown';
    }
    return {
      ...c,
      status: c.status || ('current' as const),
      data_source: dataSource as DataSource,
      source_url: effectiveSourceUrl,
      source_label: sourceLabel,
    };
  });

  // Build maps of website company names for PEM merge (multiple strategies)
  const websiteNameMap = new Map<string, number>();
  const websiteCompactMap = new Map<string, number>();
  const websiteNoGroupMap = new Map<string, number>();
  websiteCompanies.forEach((c, i) => {
    const norm = normalizeCompanyName(c.company_name);
    websiteNameMap.set(norm, i);
    websiteCompactMap.set(compactName(norm), i);
    const noGroup = norm.replace(/\bgroup\b/, '').replace(/\s+/g, ' ').trim();
    if (noGroup) websiteNoGroupMap.set(noGroup, i);
  });

  // Merge PEM deals into portfolio:
  // - If a PEM company matches a website company, enrich the website entry with PEM data
  //   (entry date, sector, deal details) while keeping the website status (current).
  // - If a PEM company is NOT on the website, add it as exited.
  const pemDeals = getDealsForFund(fundSlug);
  const pemOnlyCompanies: PortfolioCompany[] = [];
  for (const deal of pemDeals) {
    const targetCompany = normalizeViaMarker(deal.target_company);
    const normalized = normalizeCompanyName(targetCompany);
    if (normalized.length <= 2) continue;
    if (!isValidPortfolioEntry(targetCompany, fundSlug)) continue;

    // Try exact normalized → compact (space-insensitive) → group-stripped
    let websiteIdx = websiteNameMap.get(normalized);
    if (websiteIdx === undefined) websiteIdx = websiteCompactMap.get(compactName(normalized));
    if (websiteIdx === undefined) {
      const noGroup = normalized.replace(/\bgroup\b/, '').replace(/\s+/g, ' ').trim();
      if (noGroup.length > 2) websiteIdx = websiteNoGroupMap.get(noGroup);
    }
    // Strategy 4: Word-boundary substring match (min 5 chars)
    // Handles: "Frigoveneta" matching PEM "Frigoveneta Service"
    if (websiteIdx === undefined && normalized.length >= 5) {
      for (const [wsName, wsIdx] of websiteNameMap) {
        if (wsName.length < 5) continue;
        const shorter = normalized.length <= wsName.length ? normalized : wsName;
        const longer = normalized.length <= wsName.length ? wsName : normalized;
        const idx = longer.indexOf(shorter);
        if (idx === -1) continue;
        if (idx > 0 && longer[idx - 1] !== ' ') continue;
        const endIdx = idx + shorter.length;
        if (endIdx < longer.length && longer[endIdx] !== ' ') continue;
        websiteIdx = wsIdx;
        break;
      }
    }
    if (websiteIdx !== undefined) {
      // Enrich matching website entry with PEM data (don't override existing values)
      const wc = websiteCompanies[websiteIdx];
      if (!wc.entry_date) wc.entry_date = `${deal.source_year}-01-01`;
      if (!wc.sector) wc.sector = deal.sector_detail || deal.sector;
      if (!wc.region) wc.region = deal.region;
      if (!wc.investment_stage) wc.investment_stage = deal.investment_stage;
      if (!wc.invested_amount_eur_mln) wc.invested_amount_eur_mln = deal.invested_amount_eur_mln;
      if (!wc.deal_year) wc.deal_year = deal.source_year;
    } else {
      const override = getPemStatusOverride(fundSlug, deal.id, normalized);
      pemOnlyCompanies.push({
        fund_slug: fundSlug,
        company_id: `pem-${deal.id}`,
        company_name: targetCompany,
        status: override?.status ?? null,
        status_source_url: override?.source_url ?? null,
        status_source_label: override?.source_label ?? null,
        entry_date: `${deal.source_year}-01-01`,
        exit_date: null,
        confidence: 0.8,
        sector: deal.sector_detail || deal.sector,
        region: deal.region,
        investment_stage: deal.investment_stage,
        invested_amount_eur_mln: deal.invested_amount_eur_mln,
        deal_year: deal.source_year,
        data_source: 'pem' as const,
        source_url: PEM_BASE_URL,
        source_label: `PEM ${deal.source_year}`,
      });
    }
  }

  // Deduplicate PEM-only entries (same company appearing with slightly different names)
  const dedupedPem: PortfolioCompany[] = [];
  const pemSeenNormalized = new Set<string>();
  const pemSeenCompact = new Set<string>();
  for (const pc of pemOnlyCompanies) {
    const norm = normalizeCompanyName(pc.company_name);
    const compact = compactName(norm);
    if (pemSeenNormalized.has(norm) || pemSeenCompact.has(compact)) continue;
    pemSeenNormalized.add(norm);
    pemSeenCompact.add(compact);
    dedupedPem.push(pc);
  }

  const allCompanies = [...websiteCompanies, ...dedupedPem];

  // Sort: current first, then partial, then unknown, then exited.
  // Within each group: most recent entry date first, then alphabetically.
  const STATUS_ORDER: Record<string, number> = { current: 0, partial: 1, exited: 3 };
  return allCompanies.sort((a, b) => {
    const aOrder = a.status ? (STATUS_ORDER[a.status] ?? 2) : 2;
    const bOrder = b.status ? (STATUS_ORDER[b.status] ?? 2) : 2;
    if (aOrder !== bOrder) return aOrder - bOrder;
    // Most recent date first (entries with dates before entries without)
    const aDate = a.entry_date || a.investment_date || '';
    const bDate = b.entry_date || b.investment_date || '';
    if (aDate && !bDate) return -1;
    if (!aDate && bDate) return 1;
    if (aDate && bDate && aDate !== bDate) return bDate.localeCompare(aDate);
    return a.company_name.localeCompare(b.company_name);
  });
}

/**
 * Get the geographic scope label for a fund's portfolio (e.g., "Italy", "Europe", "EMEA", "Worldwide").
 * Defaults to "Italy" for funds without an explicit scope (Italian SGRs).
 */
export function getPortfolioGeoScope(fundSlug: string): string {
  const portfolios = loadPortfolios();
  const explicitScope = portfolios.geoScopes[fundSlug];
  if (explicitScope) return explicitScope;

  const fund = loadDatabase().funds.find((f) => f.slug === fundSlug);
  const geographies = (fund?.geographies || []).filter(Boolean);
  if (geographies.length > 0) {
    const unique = Array.from(new Set(geographies));
    return unique.join(' / ');
  }

  return 'Italy';
}

/**
 * Get an explanatory note for funds that don't have portfolio entries
 * (e.g., fund-of-funds, debt-only strategies).
 */
export function getPortfolioNote(fundSlug: string): string | null {
  const portfolios = loadPortfolios();
  return portfolios.portfolioNotes[fundSlug] || null;
}

/**
 * Get an explanatory note for funds that have 0 signals.
 * Checks url_status.json to determine the reason.
 */
export function getSignalNote(fundSlug: string): string | null {
  const fund = getFundBySlug(fundSlug);
  if (!fund) return null;

  // No website at all
  if (!fund.website || fund.website === 'N/A' || fund.website === '-') {
    return 'No website available for this fund. Signals are detected by monitoring fund websites for changes.';
  }

  // Check url_status.json for access issues
  let domain: string | null = null;
  try {
    const parsed = new URL(fund.website.startsWith('http') ? fund.website : `https://${fund.website}`);
    domain = parsed.hostname;
  } catch { /* ignore */ }

  if (domain) {
    const statusPath = join(getRepoRoot(), 'data', 'derived', 'url_status.json');
    if (existsSync(statusPath)) {
      try {
        const statusFile = JSON.parse(readFileSync(statusPath, 'utf-8'));
        const statuses = statusFile.statuses || {};
        const domainEntries: Array<{ status?: string; status_code?: number | null; consecutive_failures?: number }> = [];

        for (const [url, info] of Object.entries(statuses) as [string, { status?: string; status_code?: number | null; consecutive_failures?: number }][]) {
          try {
            const urlDomain = new URL(url).hostname;
            if (urlDomain === domain || urlDomain === `www.${domain}` || domain === `www.${urlDomain}`) {
              domainEntries.push(info);
            }
          } catch { /* ignore malformed URL */ }
        }

        if (domainEntries.length > 0) {
          const isHealthy = (i: { status?: string; status_code?: number | null }) => {
            const statusCode = i.status_code ?? null;
            const status = i.status ?? '';
            if (statusCode === 200 || statusCode === 304) return true;
            if (status === 'ok') return true;
            if (status === 'other_error' && statusCode === 304) return true;
            return false;
          };

          const hasHealthy = domainEntries.some(isHealthy);
          const has403 = domainEntries.some((i) => i.status_code === 403 || i.status === '403');
          const hasSslError = domainEntries.some((i) => i.status === 'ssl_error');

          const hasPersistentUnreachable = domainEntries.some((i) => {
            if (isHealthy(i)) return false;
            if (i.status_code === 403 || i.status === '403') return false;
            if (i.status === 'ssl_error') return false;
            return (i.consecutive_failures ?? 0) >= 2;
          });

          // If we still have healthy monitored URLs, avoid hard "blocked/unreachable" claims.
          if (hasHealthy) {
            if (has403) {
              return `${fund.name}'s website is partially accessible. Some sections block automated access, but monitoring continues on reachable pages.`;
            }
            return 'No notable signals detected yet. This fund\'s website is being monitored for news, deals, and team changes.';
          }

          if (has403) {
            return `${fund.name}'s website currently blocks automated access. We are working on alternative monitoring methods.`;
          }

          if (hasSslError) {
            return `${fund.name}'s website has SSL certificate issues preventing automated monitoring.`;
          }

          if (hasPersistentUnreachable) {
            return `${fund.name}'s website is currently unreachable. Monitoring will resume when access is restored.`;
          }
        }
      } catch { /* ignore parse errors */ }
    }
  }

  // Default: has website, no known issues, just no signals yet
  return 'No notable signals detected yet. This fund\'s website is being monitored for news, deals, and team changes.';
}

/**
 * LinkedIn Team Analytics
 */
interface TeamAnalyticsFile {
  generated_at: string;
  fund_count: number;
  funds: Record<string, unknown>;
}

interface ManualProfilesFile {
  funds?: { slug?: string }[];
}

let cachedTeamAnalytics: TeamAnalyticsFile | null = null;
let cachedManualLinkedinProfileFundSlugs: string[] | null = null;

function loadTeamAnalytics(): TeamAnalyticsFile {
  if (cachedTeamAnalytics) {
    return cachedTeamAnalytics;
  }

  const analyticsPath = join(getRepoRoot(), 'data', 'derived', 'linkedin', 'fund_people_stats.json');

  if (!existsSync(analyticsPath)) {
    return { generated_at: '', fund_count: 0, funds: {} };
  }

  try {
    const data = readFileSync(analyticsPath, 'utf-8');
    cachedTeamAnalytics = JSON.parse(data);
    return cachedTeamAnalytics!;
  } catch (e) {
    console.error('Failed to load team analytics:', e);
    return { generated_at: '', fund_count: 0, funds: {} };
  }
}

/**
 * Normalize flat format (from PeopleStatsCalculator) to nested TeamAnalytics format.
 * Old manually-curated entries already have the nested format and pass through unchanged.
 */
function normalizeTeamAnalytics(raw: Record<string, unknown>): TeamAnalytics {
  // Already in nested format (has `backgrounds` dict)
  if (raw.backgrounds !== undefined) {
    return raw as unknown as TeamAnalytics;
  }

  // Flat format — transform to nested
  const bgMap: Record<string, string> = {
    background_pe: 'private_equity',
    background_ib: 'investment_banking',
    background_vc: 'venture_capital',
    background_consulting: 'consulting',
    background_big_four: 'big_four',
    background_corporate: 'corporate',
    background_tech: 'tech',
    background_legal: 'legal',
    background_other: 'other',
  };
  const backgrounds: Record<string, number> = {};
  for (const [key, label] of Object.entries(bgMap)) {
    const val = (raw[key] as number) || 0;
    if (val > 0) backgrounds[label] = val;
  }

  const seniorityMap: Record<string, string> = {
    partners: 'partner',
    managing_directors: 'managing_director',
    principals: 'principal',
    directors: 'director',
    vice_presidents: 'vice_president',
    associates: 'associate',
    analysts: 'analyst',
    other_roles: 'other',
  };
  const seniority: Record<string, number> = {};
  for (const [key, label] of Object.entries(seniorityMap)) {
    const val = (raw[key] as number) || 0;
    if (val > 0) seniority[label] = val;
  }

  const genderMale = (raw.gender_male_pct as number) || 0;
  const genderFemale = (raw.gender_female_pct as number) || 0;
  const total = (raw.total_employees as number) || 0;

  return {
    fund_slug: raw.fund_slug as string,
    total_profiles: total,
    education: {
      top_schools: (raw.education_schools as Record<string, number>) || {},
      top_degrees: (raw.top_degrees as Record<string, number>) || {},
      top_majors: (raw.top_majors as Record<string, number>) || {},
      education_tier: {
        top_mba: (raw.top_mba_count as number) || 0,
        top_undergrad: (raw.top_undergrad_count as number) || 0,
        other: total - ((raw.top_mba_count as number) || 0) - ((raw.top_undergrad_count as number) || 0),
      },
    },
    backgrounds,
    seniority,
    hiring: {
      new_hires_last_1y: (raw.new_hires_last_12mo as number) || 0,
      new_hires_last_2y: (raw.new_hires_last_24mo as number) || 0,
      new_hires_last_3y: (raw.new_hires_last_36mo as number) || 0,
      new_hires_last_4y: (raw.new_hires_last_48mo as number) || 0,
      avg_tenure_years: (raw.avg_tenure_years as number) || 0,
    },
    demographics: {
      gender_male_pct: genderMale,
      gender_female_pct: genderFemale,
      gender_unknown_pct: Math.max(0, Math.round((100 - genderMale - genderFemale) * 10) / 10),
      avg_years_experience: (raw.avg_years_experience as number) || 0,
      avg_estimated_age: 0,
    },
  };
}

export function getTeamAnalyticsForFund(fundSlug: string): TeamAnalytics | null {
  const analytics = loadTeamAnalytics();
  const raw = analytics.funds[fundSlug];
  if (!raw) return null;
  return normalizeTeamAnalytics(raw as Record<string, unknown>);
}

/**
 * Global mega-funds where synthetic team analytics are misleading.
 *
 * IMPORTANT:
 * - This set controls only dummy-data exclusion and scraping skip behavior.
 * - It is NOT the source of truth for "Italy-only manual profiles" notes.
 * - Italy-only note coverage must come from linkedin/manual_profiles.json.
 */
const MEGA_FUNDS = new Set([
  "blackstone",  // 50k+ global employees on LinkedIn
  "kkr",  // 10k+ global employees on LinkedIn
  "apollo",  // 3k+ global, multi_strategy, NY HQ
  "ares-management",  // 3k+ global, multi_strategy, LA HQ
  "macquarie",  // 20k+ global, infra, London HQ
  "towerbrook",  // 500+ global, PE, NY HQ
]);

function loadManualLinkedinProfileFundSlugs(): string[] {
  if (cachedManualLinkedinProfileFundSlugs) return cachedManualLinkedinProfileFundSlugs;

  const manualPath = join(getRepoRoot(), 'data', 'derived', 'linkedin', 'manual_profiles.json');
  if (!existsSync(manualPath)) {
    cachedManualLinkedinProfileFundSlugs = [];
    return cachedManualLinkedinProfileFundSlugs;
  }

  try {
    const data = JSON.parse(readFileSync(manualPath, 'utf-8')) as ManualProfilesFile;
    const aliases = loadAliases();
    const slugs = new Set<string>();
    for (const fund of data.funds || []) {
      const rawSlug = (fund.slug || '').trim();
      if (!rawSlug) continue;
      const normalizedSlug = aliases[rawSlug] || rawSlug;
      slugs.add(normalizedSlug);
    }
    cachedManualLinkedinProfileFundSlugs = [...slugs];
  } catch (e) {
    console.error('Failed to load manual LinkedIn profiles:', e);
    cachedManualLinkedinProfileFundSlugs = [];
  }

  return cachedManualLinkedinProfileFundSlugs;
}

export function isMegaFund(fundSlug: string): boolean {
  return MEGA_FUNDS.has(fundSlug);
}

export function isManualLinkedinProfileFund(fundSlug: string): boolean {
  return loadManualLinkedinProfileFundSlugs().includes(fundSlug);
}

export function getAllRealAnalytics(): Record<string, TeamAnalytics> {
  const raw = loadTeamAnalytics().funds;
  const result: Record<string, TeamAnalytics> = {};
  for (const [slug, entry] of Object.entries(raw)) {
    result[slug] = normalizeTeamAnalytics(entry as Record<string, unknown>);
  }
  return result;
}

/**
 * Return funds with only the fields needed for the homepage table.
 * Avoids serializing description, contacts, AIFI metrics, etc. to the client.
 */
export function getAllFundsSlim(): FundSlim[] {
  return getAllFunds().map(f => ({
    id: f.id,
    slug: f.slug,
    name: f.name,
    category: f.category,
    hq_city: f.hq_city,
    hq_region: f.hq_region,
    offices: f.offices,
    website: f.website,
    sector_tags: f.sector_tags,
    strategy_tags: f.strategy_tags,
    geographies: f.geographies,
    average_investment: f.average_investment,
    aum_eur: f.aum_eur,
    investment_min_eur: f.investment_min_eur ?? null,
    investment_max_eur: f.investment_max_eur ?? null,
  }));
}

export interface FundSlim {
  id: string;
  slug: string;
  name: string;
  category: Fund['category'];
  hq_city: string | null;
  hq_region: string | null;
  offices?: Fund['offices'];
  website: string | null;
  sector_tags: string[];
  strategy_tags: string[];
  geographies?: string[];
  average_investment?: string[];
  aum_eur?: number | null;
  investment_min_eur?: number | null;
  investment_max_eur?: number | null;
}

export function getMegaFundSlugs(): string[] {
  return [...MEGA_FUNDS];
}

export function getManualLinkedinProfileFundSlugs(): string[] {
  // Source of truth for "Italy-only profiles" annotation.
  return loadManualLinkedinProfileFundSlugs();
}

/**
 * Sort offices: Italian first, then HQ, then alphabetical by city.
 */
export function getSortedOffices(fund: Fund): Office[] {
  if (!fund.offices || fund.offices.length === 0) return [];
  return [...fund.offices].sort((a, b) => {
    if (a.is_italy !== b.is_italy) return a.is_italy ? -1 : 1;
    if (a.is_hq !== b.is_hq) return a.is_hq ? -1 : 1;
    return a.city.localeCompare(b.city);
  });
}

// ── Company aggregation (cross-fund) ───────────────────────────────────────

let cachedCompanies: Company[] | null = null;

/**
 * Aggregate all portfolio companies across all funds into deduplicated Company entries.
 * Uses existing getPortfolioForFund() (already cached) for each fund.
 * Deduplicates by compactName(normalizeCompanyName(name)) — same key used within-fund.
 */
export function getAllCompanies(): Company[] {
  if (cachedCompanies) return cachedCompanies;

  const funds = getAllFunds();
  const fundNameMap = new Map<string, string>();
  for (const f of funds) fundNameMap.set(f.slug, f.name);

  // Group portfolio entries by normalized company key
  const companyMap = new Map<string, {
    displayName: string;
    sector: string | null;
    website: string | null;
    description: string | null;
    headquarters: string | null;
    investments: CompanyInvestment[];
  }>();

  for (const fund of funds) {
    const portfolio = getPortfolioForFund(fund.slug);
    for (const item of portfolio) {
      const key = compactName(normalizeCompanyName(item.company_name));
      if (!key || key.length <= 1) continue;

      const existing = companyMap.get(key);
      const investment: CompanyInvestment = {
        fund_slug: fund.slug,
        fund_name: fundNameMap.get(fund.slug) || fund.slug,
        status: item.status,
        entry_date: item.entry_date || item.investment_date || null,
        exit_date: item.exit_date || null,
        data_source: item.data_source || null,
        source_url: item.source_url || null,
        source_label: item.source_label || null,
        invested_amount_eur_mln: item.invested_amount_eur_mln || null,
        investment_stage: item.investment_stage || null,
        deal_year: item.deal_year || null,
      };

      if (existing) {
        // Pick longest display name
        if (item.company_name.length > existing.displayName.length) {
          existing.displayName = item.company_name;
        }
        // Fill missing metadata from any fund
        if (!existing.sector && item.sector) existing.sector = item.sector;
        if (!existing.website && item.website) existing.website = item.website;
        if (!existing.description && item.description) existing.description = item.description;
        if (!existing.headquarters && item.headquarters) existing.headquarters = item.headquarters;
        existing.investments.push(investment);
      } else {
        companyMap.set(key, {
          displayName: item.company_name,
          sector: item.sector || null,
          website: item.website || null,
          description: item.description || null,
          headquarters: item.headquarters || null,
          investments: [investment],
        });
      }
    }
  }

  // Filter out fund vehicles, SGRs, and other non-company entities.
  // Applied here (not in isValidPortfolioEntry) so fund detail pages can still show
  // legitimate acquisitions of fund entities (e.g. Blackstone → Kryalos SGR).
  const FUND_ENTITY_PATTERNS = [
    /\bfund\s*(?:\([^)]*\))?\s*$/i,    // ends with "Fund" or "Fund (X)" — fund vehicles
    /\bSGR\b/i,                          // Italian fund management companies (Società di Gestione del Risparmio)
    /\bcapital\s+portfolio\b/i,          // "X Capital Portfolio" — fund portfolio labels
    /^fondo$/i,                          // bare "Fondo" — incomplete entry
  ];

  function isFundEntity(name: string): boolean {
    return FUND_ENTITY_PATTERNS.some(pat => pat.test(name.trim()));
  }

  // Convert to Company[] sorted alphabetically
  const companies: Company[] = [];
  for (const [, data] of companyMap) {
    if (isFundEntity(data.displayName)) continue;
    companies.push({
      slug: slugify(normalizeCompanyName(data.displayName)) || slugify(data.displayName),
      name: data.displayName,
      sector: data.sector,
      website: data.website,
      description: data.description,
      headquarters: data.headquarters,
      investments: data.investments,
    });
  }

  companies.sort((a, b) => a.name.localeCompare(b.name));
  cachedCompanies = companies;
  return cachedCompanies;
}

export function getCompanyBySlug(slug: string): Company | undefined {
  return getAllCompanies().find(c => c.slug === slug);
}

export interface CompanySlim {
  slug: string;
  name: string;
  sector: string | null;
  headquarters: string | null;
  investmentCount: number;
  hasCurrentInvestment: boolean;
  allExited: boolean;
}

export function getAllCompaniesSlim(): CompanySlim[] {
  return getAllCompanies().map(c => ({
    slug: c.slug,
    name: c.name,
    sector: c.sector,
    headquarters: c.headquarters,
    investmentCount: c.investments.length,
    hasCurrentInvestment: c.investments.some(inv => inv.status === 'current'),
    allExited: c.investments.length > 0 && c.investments.every(inv => inv.status === 'exited'),
  }));
}

// ── Company signals (from enriched signals with target_companies) ────────────

export interface CompanySignal extends Signal {
  fund_name: string;
  fund_slug: string;
}

let cachedCompanySignalIndex: Map<string, CompanySignal[]> | null = null;

function buildCompanySignalIndex(): Map<string, CompanySignal[]> {
  if (cachedCompanySignalIndex) return cachedCompanySignalIndex;

  const index = new Map<string, CompanySignal[]>();

  // Read enriched signals file directly (same as loadFilteredSignals but we need target_companies)
  const repoRoot = getRepoRoot();
  const enrichedPath = join(repoRoot, 'data', 'derived', 'detected_signals_enriched.json');
  if (!existsSync(enrichedPath)) {
    cachedCompanySignalIndex = index;
    return index;
  }

  let rawSignals: Array<Record<string, unknown>>;
  try {
    const data = readFileSync(enrichedPath, 'utf-8');
    const file = JSON.parse(data);
    rawSignals = file.signals || [];
  } catch (e) {
    console.error('Failed to load enriched signals for company index:', e);
    cachedCompanySignalIndex = index;
    return index;
  }

  // Build fund slug → name lookup
  const fundNameMap = new Map<string, string>();
  for (const f of getAllFunds()) fundNameMap.set(f.slug, f.name);

  const knownFundNames = buildKnownFundNames(getAllFunds());

  for (const raw of rawSignals) {
    const targetCompanies = raw.target_companies as Array<{ name: string }> | undefined;
    if (!targetCompanies || targetCompanies.length === 0) continue;

    const signal = raw as unknown as Signal;
    if (signal.signal_type === 'website_change') continue;

    // Apply signal processing (same as getSignalsForFund)
    const fundSlug = (signal.fund_slug || '') as string;
    if (isGarbageSignal({ ...signal, fund_slug: fundSlug }, knownFundNames)) continue;

    const cleanedTitle = cleanSignalText(cleanSignalTitle(signal.title || ''));
    const cleanedWhatChanged = cleanSignalText(signal.what_changed || '');
    const newType = reclassifySignalType({ ...signal, title: cleanedTitle, what_changed: cleanedWhatChanged });
    const isDupText = isRedundantSignalSummary(cleanedTitle, cleanedWhatChanged);

    const processedSignal: CompanySignal = {
      ...signal,
      title: cleanedTitle,
      what_changed: isDupText ? '' : cleanedWhatChanged,
      ...(newType ? { signal_type: newType } : {}),
      fund_slug: fundSlug,
      fund_name: fundNameMap.get(fundSlug) || fundSlug.replace(/-/g, ' '),
    };

    for (const tc of targetCompanies) {
      if (!tc.name) continue;
      const key = compactName(normalizeCompanyName(tc.name));
      if (!key || key.length <= 1) continue;
      const existing = index.get(key) || [];
      existing.push(processedSignal);
      index.set(key, existing);
    }
  }

  cachedCompanySignalIndex = index;
  return index;
}

/**
 * Get signals mentioning a specific portfolio company.
 * Uses target_companies from enriched signals, matched by normalized name.
 * Only returns signals where fund_slug is in the company's investor set.
 */
export function getSignalsForCompany(companySlug: string): CompanySignal[] {
  const company = getCompanyBySlug(companySlug);
  if (!company) return [];

  const index = buildCompanySignalIndex();
  const key = compactName(normalizeCompanyName(company.name));
  const candidates = index.get(key) || [];
  if (candidates.length === 0) return [];

  // Only keep signals from funds that actually invested in this company
  const investorSlugs = new Set(company.investments.map(inv => inv.fund_slug));
  const filtered = candidates.filter(s => investorSlugs.has(s.fund_slug));

  // Deduplicate by source_url + title + published_at
  const seen = new Set<string>();
  const deduped = filtered.filter(s => {
    const dedupKey = `${s.source_url}::${s.title}::${s.published_at || ''}`;
    if (seen.has(dedupKey)) return false;
    seen.add(dedupKey);
    return true;
  });

  // Sort by date descending (published_at preferred, fallback to observed_at)
  return deduped.sort((a, b) => {
    const dateA = a.published_at || a.observed_at;
    const dateB = b.published_at || b.observed_at;
    return dateB.localeCompare(dateA);
  });
}
