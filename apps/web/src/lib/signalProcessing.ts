/**
 * Shared signal processing functions for Fundradar
 *
 * Used by both data.ts (fund detail pages) and signals_unified.ts (signals feed).
 * Canonical implementations extracted from data.ts to eliminate dual-path inconsistency.
 */

import type { Signal, SignalType } from '@fundradar/shared';

// ── Shared regex patterns for signal reclassification ────────────────────────
// Extracted from reclassifySignalType() to reduce duplication.

/** Strong exit verbs — "Fund sells/cede X" is always an exit */
const RE_EXIT_VERBS = /\b(?:sells?|sold|vend(?:e|ere|ita|ono)|vendut[oa]|cede|cession[ei]|disinvest\w+|divest\w+|exits?|exited|realis(?:ation|ed)|realiz(?:ation|ed))\b/i;

/** Acquisition counter-pattern — blocks exit classification when present */
const RE_ACQUISITION_VERBS = /\b(?:acquir\w+|acquisizion\w+|rileva|buys?|compra)\b/i;

/** PE action verbs — broad check for any PE-relevant language (blocks demotions) */
const RE_PE_ACTION_VERBS = /\b(?:acqui\w+|investi\w+|rileva|exit|sells?|cessione|fundrais\w+|raccolta|round)\b/i;

/** PE action verbs — extended variant used for event/conference demotions */
const RE_PE_ACTION_VERBS_EXTENDED = /\b(?:acqui|invest|rileva|entra|buyout|merger|fusion[ei]|exit|sells?|sold|cessione)\b/i;

/** Non-equity instruments — blocks debt_financing reclassification */
const RE_NON_DEBT_VERBS = /\b(?:acqui\w+|rileva|investiment[oi]|exit|sells?|cessione|launch|lancia|nasce)\b/i;

/** Italian job selection patterns */
const RE_JOB_SELECTION = /\b(?:procedura\s+di\s+selezione|ricerca\s+(?:una?\s+)?risors[ae]|avvia\s+(?:la\s+)?selezione|selezione\s+per\s+(?:il\s+)?(?:ruolo|responsabile|posizione)|(?:tempo\s+)?(?:pieno|indeterminato|determinato)(?:\s+e\s+indeterminato)?)\b/i;

// ── Shared signal type display config ─────────────────────────────────────────
// Single source of truth for signal type labels and colors.
// Used by both SignalsFeed (signals page) and SignalsCompact (fund page).

/** Signal types that are grouped under the "Fund" display category */
export const FUND_SIGNAL_TYPES: SignalType[] = ['fundraise_announced', 'fundraise_closed', 'fund_launch'];

/** Signal types that are grouped under the "People" display category */
export const PEOPLE_SIGNAL_TYPES: SignalType[] = ['people_move', 'job_posting'];

/** Collapsed display type (fundraise→fund, people_move+job_posting→people, deal_announced→investment) */
export type DisplaySignalType = Exclude<SignalType, 'fundraise_announced' | 'fundraise_closed' | 'fund_launch' | 'people_move' | 'job_posting' | 'deal_announced'> | 'fund' | 'people' | 'investment';
// Note: portfolio_update passes through as-is (not collapsed)

export const toDisplayType = (type: SignalType): DisplaySignalType =>
  FUND_SIGNAL_TYPES.includes(type) ? 'fund' : PEOPLE_SIGNAL_TYPES.includes(type) ? 'people' : type === 'deal_announced' ? 'investment' : type as DisplaySignalType;

export interface SignalTypeStyle {
  label: string;
  bg: string;
  color: string;
}

export const SIGNAL_TYPE_STYLES: Record<string, SignalTypeStyle> = {
  investment:        { label: 'Investment', bg: '#e8f5e9', color: '#2e7d32' },
  fund:              { label: 'Fund', bg: '#e3f2fd', color: '#0d47a1' },
  exit_announced:    { label: 'Exit', bg: '#fff3e0', color: '#e65100' },
  debt_financing:    { label: 'Debt', bg: '#fff8e1', color: '#f57f17' },
  partnership:       { label: 'Partnership', bg: '#e0f2f1', color: '#00695c' },
  people:            { label: 'People', bg: '#f3e5f5', color: '#7b1fa2' },
  portfolio_update:  { label: 'Portfolio', bg: '#ede7f6', color: '#4527a0' },
  report:            { label: 'Report', bg: '#e0f7fa', color: '#006064' },
  website_change:    { label: 'Website', bg: '#fce4ec', color: '#c2185b' },
  other:             { label: 'Other', bg: '#f5f5f5', color: '#616161' },
};

/**
 * Importance bonus by raw signal type (used for sort ranking on /signals page).
 * Keyed by raw SignalType (not display type) since ranking needs fine-grained
 * distinction (e.g., fundraise_closed > fundraise_announced).
 * Single source of truth — imported by SignalsFeed.tsx.
 */
export const SIGNAL_TYPE_IMPORTANCE: Record<string, number> = {
  deal_announced: 15,
  exit_announced: 15,
  fundraise_closed: 12,
  fund_launch: 10,
  fundraise_announced: 8,
  debt_financing: 6,
  partnership: 6,
  portfolio_update: 6,
  people_move: 5,
  job_posting: 5,
  report: 4,
};

/**
 * Detect garbage signals where the title contains a nav element, section heading,
 * or other non-informative text extracted by mistake from the fund website.
 */
/**
 * Build a set of known fund names for misattribution detection.
 * Auto-generated from fund data — no hardcoded list needed.
 */
export function buildKnownFundNames(funds: Array<{ name: string }>): Set<string> {
  const names = new Set<string>();
  for (const fund of funds) {
    const name = (fund.name || '').trim().toLowerCase();
    if (!name) continue;
    names.add(name);
    // Add first word as brand shorthand (e.g. "blackstone" from "Blackstone Group")
    const words = name.split(/\s+/);
    if (words.length > 1 && words[0].length > 2) {
      names.add(words[0]);
    }
  }
  // External counterparties not in db.json but common in Italian PE news
  for (const n of ['tpg', 'johnson & johnson', 'j&j', 'warburg', 'cinven', 'deep ocean', 'p 101', '360 capital', 'xenon', 'mandarin']) {
    names.add(n);
  }
  return names;
}

export function isGarbageSignal(signal: Signal, knownFundNames?: Set<string>): boolean {
  const title = signal.title || '';
  const whatChanged = signal.what_changed || '';

  // Garbage company names extracted as deal/investment targets
  const GARBAGE_TARGETS = [
    'current portfolio', 'prior investments', 'portfolio overview',
    'sectors', 'strategy', 'portafoglio', 'business advisors',
    'our companies', 'homepage', 'back to homepage',
  ];
  const titleLower = title.toLowerCase();
  for (const target of GARBAGE_TARGETS) {
    if (titleLower.includes(target) && /new (?:investment|deal)/i.test(titleLower)) return true;
  }

  // Portfolio section headers (fund-internal identifiers, not company names)
  // e.g. "INVESTIMENTI GAPEF 3 TFM Automotive&Industry", "REALIZZATE FONDO Q2 Fine Sounds"
  if (/^(?:investimenti|realizzate|realizzati|operazioni|partecipazioni)\s+(?:fondo|del\s+fondo|gapef|[a-z]+\s+\d)/i.test(titleLower)) return true;

  // Italian website section headers misextracted as portfolio companies
  // e.g. "Esigenze dell'impresa target", "Settori di intervento", "Tipologia di investimento"
  if (/^(?:esigenz[ei]|requisiti|criteri|caratteristiche|tipologi[ae]|settori?\s+di|informazion[ie]|contatti|mission[ei]?|strategi[ae]|chi\s+siamo|about\s+us|il\s+nostro|la\s+nostra|i\s+nostri|le\s+nostre)\b/i.test(titleLower)) return true;

  // Pure navigation/UI text extracted as signal titles (not deal-specific check)
  const NAV_SIGNAL_TITLES = [
    'back to top', 'back to homepage', 'homepage', 'menu',
    'search', 'next', 'previous', 'close', 'cookie policy',
    'privacy policy', 'portafoglio', 'contatti',
  ];
  if (NAV_SIGNAL_TITLES.includes(titleLower.trim())) return true;

  // Pipe-separated navigation text: "Entity | Press releases", "Fund | News", etc.
  // These are website breadcrumbs/section headers scraped as signals, not real events.
  const wcPipeLower = whatChanged.toLowerCase().trim();
  if (
    / \| (?:press releases?|news|insights?|publications?|media|resources?|announcements?|articles?|updates?|events?|about|team|contact|portfolio|careers?)\s*$/i.test(whatChanged) ||
    (wcPipeLower.includes(' | ') && wcPipeLower.length < 60 && !/\b(?:acqui|invest|rilev|exit|sell|rais|launch|clos|deal|fund)\w*/i.test(wcPipeLower))
  ) {
    return true;
  }

  // what_changed is just a newspaper/source name (not a description of what happened)
  const wcLower = whatChanged.toLowerCase().trim();
  if (wcLower && wcLower.length < 60) {
    // --- Italian national business/finance dailies & magazines ---
    const NEWSPAPER_EXACT = [
      'il sole 24 ore', 'milano finanza', 'italia oggi',
      // --- General newspapers with economia desks ---
      'corriere della sera', 'la repubblica', 'la stampa',
      'il messaggero', 'il foglio', 'il fatto quotidiano',
      'avvenire', 'libero', 'il tempo', 'panorama',
      'il giorno', 'la nazione', 'il mattino', 'il tirreno',
      'il piccolo', 'brescia oggi', 'il resto del carlino',
      'il quotidiano', 'tuttosport',
      // --- Vertical/trade press (PE/VC, finance, startup) ---
      'bebeez', 'financecommunity.it', 'financecommunity',
      'economyup', 'economy up', 'startupitalia', 'startup italia',
      'economy', 'private equity wire', 'pe hub',
      // --- Supplements & inserts ---
      'affari & finanza', 'affari e finanza', 'l\'economia',
      // --- International sources cited in Italian PE ---
      'financial times', 'bloomberg', 'reuters', 'forbes',
      'the wall street journal', 'wall street journal',
    ];
    if (NEWSPAPER_EXACT.includes(wcLower)) return true;
    // Pattern: all "Corriere *" variants are Italian newspapers
    if (/^corriere\b/i.test(wcLower)) return true;
    // Pattern: all "Gazzetta *" variants are Italian newspapers
    if (/^(?:la )?gazzetta\b/i.test(wcLower)) return true;
    // Pattern: regional papers "La Provincia di X", "La Voce di X", "Il Giornale di X", etc.
    if (/^(?:la provincia|la voce|il giornale|il secolo|il quotidiano)\s+(?:di|del|della|dello|dell'|d')\s+/i.test(wcLower)) return true;
    // Pattern: "MF-Milano Finanza", "MF Newswires", "QN Quotidiano Nazionale"
    if (/^(?:mf[\s-]|qn\s)/i.test(wcLower)) return true;
    // Pattern: "Il Sole 24 Ore" section variants like "Il Sole 24 Ore - Plus24"
    if (/^il sole 24 ore\b/i.test(wcLower)) return true;
  }

  // what_changed is just generic about/marketing text (>100 chars with no news value)
  if (wcLower.length > 100 && /purpose-driven|global investment organization/i.test(wcLower)) return true;

  // Non-Italy signals: italy_relevant=false means the relevance scorer found no Italy connection.
  // Only apply this safety net to RAW/unfiltered signals (no quality_score).
  // Signals that already passed Python's filter (have quality_score) are trusted —
  // the Python geo-relevance gate is the authoritative check.
  const sigAny = signal as any;
  if (sigAny.italy_relevant === false && !sigAny.quality_score) {
    const allText = (title + ' ' + whatChanged).toLowerCase();
    const EU_MENTION = /\b(?:italy|italia|italian[aoi]?|europe|european|eu|emea|milan[oa]?|rome?|roma|torino|turin|napoli|naples|bologna|firenze|florence|genova|padova|verona|venezia|venice)\b/i;
    // If scorer says not Italy-relevant AND text has no Italy/Europe mention, filter it
    if (!EU_MENTION.test(allText)) return true;
  }

  // Signal misattribution: signal text mentions a DIFFERENT fund/SGR than the one it's tagged to.
  if (signal.fund_slug) {
    const fundName = signal.fund_slug.replace(/-/g, ' ').toLowerCase();
    const combined = (title + ' ' + whatChanged).toLowerCase();
    // Generic words that appear before "SGR" but aren't distinctive fund names
    const GENERIC_SGR_PREFIXES = new Set([
      'capital', 'alternative', 'investimenti', 'equity', 'asset', 'real',
      'venture', 'private', 'infra', 'infrastructure', 'la', 'il', 'lo',
    ]);
    // Check if the signal explicitly names a different SGR (e.g. "ACP sgr", "Nextalia SGR")
    // Skip for RSS/news signals — they legitimately mention multiple funds in context.
    // Website Monitor signals come from a single fund's website, so an SGR mismatch = misattribution.
    const isWebsiteMonitor = signal.source_name === 'Website Monitor';
    if (isWebsiteMonitor) {
      const sgrMention = combined.match(/\b((?:[a-z]{2,}\s+){0,3}[a-z]{2,})\s+sgr\b/i);
      if (sgrMention) {
        const mentionedWords = sgrMention[1].toLowerCase().split(/\s+/);
        // Filter out generic words — they're fund suffixes, not distinctive names
        const nonGeneric = mentionedWords.filter(w => !GENERIC_SGR_PREFIXES.has(w));
        if (nonGeneric.length > 0) {
          // Check if any non-generic word from the mentioned SGR is in the fund's name/slug
          const fundWords = fundName.toLowerCase().split(/[\s-]+/);
          const isOwnFund = nonGeneric.some(w => fundWords.some(fw => fw.includes(w) || w.includes(fw)));
          if (!isOwnFund) {
            return true;
          }
        }
      }
    }

    // Check if the title starts with a different known fund/entity name
    // Uses db.json-derived set when available, skips check otherwise
    if (knownFundNames) {
      const titleLowerTrimmed = titleLower.trim();
      for (const knownFund of knownFundNames) {
        if (titleLowerTrimmed.startsWith(knownFund + ' ') || titleLowerTrimmed.startsWith(knownFund + ':')) {
          // Check if the known fund name is NOT part of the tagged fund's own slug
          const knownNorm = knownFund.replace(/\s+/g, '-').replace(/&/g, '');
          if (!fundName.includes(knownNorm.replace(/-/g, ' ')) && !knownNorm.replace(/-/g, ' ').includes(fundName.split(' ')[0])) {
            return true;
          }
        }
      }
    }
  }

  // Stock photo descriptions extracted as investment targets
  if (/new (?:investment|deal)/i.test(titleLower)) {
    const afterColon = titleLower.replace(/^.*?:\s*/, '');
    // Image description patterns (photo/photograph/image of...)
    if (/^(?:photo(?:gra\w*)?|image|picture)\s+of\s/i.test(afterColon)) return true;
    // Person/people description patterns (stock photo alt text)
    if (/^(?:man|woman|person|father|mother|teenager|young|girl|boy|child|people|three|two)\s+\w+\s+\w+/i.test(afterColon)) return true;
    // Activity/scene keywords common in stock photo alt text
    if (/\b(?:sitting|standing|hugging|emerging|smiling|chemist|laboratory|wheelchair|laptops?|escalator|warehouse|driving|eating|cooking|working)\b/i.test(afterColon)) return true;
    // Object descriptions (not company names)
    if (/^(?:fibre|cable|yellow|green|blue|red|white|black)\s+\w+s?$/i.test(afterColon)) return true;
    // Article headlines mistaken for company names (e.g. Blackstone insight articles)
    if (/\?\s*$/.test(afterColon)) return true; // "Why Should You Care About Data Centers?"
    if (/^\d{4}\s/.test(afterColon)) return true; // "2026 Investment Perspectives"
    // Article-style language: "X Enters the Y", "X Reaches a Y" (not company names)
    if (/\b(?:enters?|reaches?|begins?|faces?)\s+(?:a|an|the|its?)\s/i.test(afterColon)) return true;
    // Very long deal targets with punctuation are article headlines, not company names
    if (afterColon.length > 60 && /[:,]/.test(afterColon)) return true;
    // Single-word navigation/section names extracted as company names (cdp-equity "Portfolio")
    if (/^(?:portfolio|team|news|about|contacts?|careers?|home|investments?)$/i.test(afterColon.trim())) return true;
  }

  // Form/UI placeholder text extracted as signals (any language)
  if (/\b(?:lascia\s+un\s+commento|leave\s+a\s+comment|submit|subscribe\s+to)\b/i.test(titleLower)) return true;

  // Generic slogan/tagline detection: motivational phrases are not news signals
  if (/^(?:success|together|delivering|building|creating|investing|committed)\s+\w+\s+\w+\s+\w+\s+\w+/i.test(titleLower) &&
      !/\b(?:acqui|invest(?:ed|ment)|complet|announc|clos(?:ed|ing)|rais(?:ed|ing)|launch)/i.test(titleLower)) {
    return true;
  }

  // Page structure changes posing as signals
  if (/news list update/i.test(titleLower)) return true;

  // Truncated titles ending with dangling prepositions (incomplete extraction)
  if (/\s(?:with|in|of|for|and|to|the|a|an|di|del|della|con|per|che|un|una)\s*$/i.test(title.trim())) return true;

  // Titles too short to be useful (< 15 chars)
  if (title.trim().length < 15) return true;

  // Team baseline signals: TEAM page listing existing members (not actual personnel moves)
  const pageType = ((signal as any).page_type || '').toUpperCase();
  if ((pageType === 'TEAM' || pageType === 'TEAM_LIST') && signal.signal_type === 'people_move') {
    const wc = signal.what_changed || '';
    const parenCount = (wc.match(/\([^)]+\)/g) || []).length;
    if (parenCount >= 2) return true;
    // Title with "(+N more)" from team baseline scrape
    if (/\(\+\d+ more\)/.test(title)) return true;
    // Non-senior roles: filter out administrative/support staff — not actionable signals
    // Only check single-person additions (the ones that survive the baseline filter above)
    // NOTE: `front office` is approximate for Italian PE — in Italian finance it can
    // refer to client-facing investment roles, not just admin. Acceptable trade-off
    // since most TEAM page "front office" entries are administrative (L1 audit note).
    const NON_SENIOR_ROLES = /\b(?:intern|stagist[ae]|tirocinant[ei]|account(?:ant|ing)|contabil|secretary|segretari[ao]|receptionist|administrative|amministrativ[ao]|assistant[ei]?|office\s+manager|hr\s+(?:specialist|assistant|coordinator)|human\s+resources\s+(?:specialist|assistant)|it\s+support|data\s+entry|back\s+office|front\s+office)\b/i;
    if (NON_SENIOR_ROLES.test(wc)) return true;
  }

  // Editorial/spotlight content: profiles, interviews, podcasts — not actionable signals
  if (/\b(?:spotlight|fireside\s+chat|thought\s+leadership|opinion\s+piece|editorial)\b/i.test(titleLower) &&
      !/\b(?:acqui|invest|rilev|sell|exit|launch|rais|clos|announc|complet)/i.test(titleLower)) {
    return true;
  }

  // Portfolio/investment page extractions: company names scraped as deal signals
  const sourceUrl = signal.source_url || '';
  if (/\/(portfolio|investments?|partecipazioni)\/?(?:\?|#|$)/i.test(sourceUrl)) {
    const hasActionVerb = /\b(?:invest|acqui|rilev|entr|complet|announc|sign|cede|vend|sell|sold|exit|launch|rais|clos|chiud|raccog|partner|addition)/i.test(titleLower);
    if (!hasActionVerb && title.trim().length < 80) return true;
  }

  // "Historical:" prefix — archived signals from old fund pages, not current events
  if (/^historical:/i.test(titleLower)) return true;

  // Internal dealing / regulatory notices — not useful to PE audience
  if (/\b(?:internal dealing|soggetto rilevante|MAR\b|APRA\b.*requirements?|liquidity add-on|procedura congiunta.*diritto di acquisto)\b/i.test(titleLower)) return true;

  // Event attendance that slipped through reclassification
  if (/\bguest\s+at\b.*\b(?:edition|congress|summit|conferenz|forum)\b/i.test(titleLower)) return true;

  // Vague "New investment involving [region]" with no company name
  if (/^new\s+(?:investment|deal)\s+involving\s+(?:latin\s+america|europe|asia|africa|middle\s+east|north\s+america|the\s+\w+\s+region)\s*$/i.test(title.trim())) return true;

  // Generic fund/program descriptions without a specific deal or event
  if (/^(?:investire in innovazione|seed per il sud\b)/i.test(titleLower)) return true;

  // "INSIGHT:" / "INSIGHTS:" prefix — market commentary, not actionable deal signals
  if (/^insights?\s*:/i.test(titleLower) && !RE_PE_ACTION_VERBS.test(titleLower)) return true;

  // Pipe suffix garbage: "Entity | Deals" / "Entity | deals?" = website nav scraped as signal
  if (/ \| (?:deals?|transactions?|case\s+studi\w*|success\s+stories?)\s*$/i.test(whatChanged)) return true;

  // Award announcements for non-Italy funds (Best Spanish/French/German LBO Fund etc.)
  if (/\bbest\s+(?:spanish|french|german|portuguese|nordic|nordic|uk|british)\s+(?:lbo|pe|vc|buyout|fund)\b/i.test(titleLower)) return true;

  // Thought leadership / "What it takes to X" article titles — not deal signals
  if (/\bwhat\s+it\s+(?:really\s+)?takes?\s+to\b/i.test(titleLower) &&
      !RE_PE_ACTION_VERBS.test(titleLower)) return true;

  // "Bringing together investors" / corporate event hosting — not a deal signal
  if (/\bbrings?\s+together\b.*\b(?:investors?|portfolio|limited\s+partners?)\b/i.test(titleLower) &&
      !RE_PE_ACTION_VERBS.test(titleLower)) return true;

  // Podcast episode titles (contain fund name + "|" + guest name format)
  if (/\|\s*(?:deals?\s+com|dealing\s+with|episode\s+\d|ep\.\s*\d)/i.test(titleLower)) return true;

  // Image/product dimensions embedded in titles: "480 X 480" or "480 X 480 added to portfolio"
  // Catch both "added to portfolio" form AND bare dimension strings with no PE action verb
  if (/\b\d{2,4}\s*[Xx×]\s*\d{2,4}\b/.test(titleLower) &&
      (/\badded\s+to\b/i.test(titleLower) || !/\b(?:acqui|invest|rilev|exit|sell|rais|launch|clos|deal|fund)\w*/i.test(titleLower))) return true;

  // Serialized thought-leadership / editorial series: "(Part 1 of 2)" — not a deal signal
  if (/\bpart\s+\d+\s+of\s+\d+\b/i.test(titleLower) && !RE_PE_ACTION_VERBS.test(titleLower)) return true;

  return false;
}

/**
 * Clean signal titles: fix concatenation artifacts from web scraping.
 * e.g. "Press releaseAdvent and Nextalia..." -> "Advent and Nextalia..."
 */
export function cleanSignalTitle(title: string): string {
  // Strip "more details" concatenated to end (Investindustrial extractor artifact)
  let cleaned = title.replace(/more\s*details\s*$/i, '').trimEnd();
  // Strip "Approfondisci" suffix (Gradiente SGR extractor artifact — "read more" button text)
  cleaned = cleaned.replace(/\s*Approfondisci\s*$/i, '').trimEnd();
  // Strip "LEGGI TUTTO" prefix (Invitalia extractor artifact — "read all" button text)
  cleaned = cleaned.replace(/^LEGGI\s+TUTTO\s*/i, '');
  // Strip "Read more" suffix (generic extractor artifact)
  cleaned = cleaned.replace(/\s*Read\s+more\s*$/i, '').trimEnd();
  // Insert space before ALL-CAPS word concatenated to lowercase (e.g. "aNEVERHACK" → "a NEVERHACK")
  cleaned = cleaned.replace(/([a-z])([A-Z]{3,})/g, '$1 $2');
  // Portfolio addition/removal signals: preserve context but clean fund name repetition
  // "NPO Torino added to Fund SGR portfolio (ICT)" → "New portfolio addition: NPO Torino (ICT)"
  cleaned = cleaned.replace(/(.+?)\s+added to\s+.+?\s+portfolio(?:\s*(\(.*?\)))?\s*$/i, (_, company, sector) =>
    `New portfolio addition: ${company.trim()}${sector ? ' ' + sector : ''}`);
  // Italian equivalent: "aggiunto/a al portafoglio di X"
  cleaned = cleaned.replace(/(.+?)\s+aggiunt[oa]\s+al?\s+portafoglio\s+.+$/i, (_, company) =>
    `New portfolio addition: ${company.trim()}`);
  // Strip "Press release" prefix (with or without space/separator after it)
  cleaned = cleaned.replace(/^Press\s*release\s*/i, '');
  // Strip press release dateline: "MILAN – November 25,2025 –" or "ROME, January 15 2026 –"
  cleaned = cleaned.replace(/^[A-Z][A-Z\s,]+[–\-—]+\s*(?:January|February|March|April|May|June|July|August|September|October|November|December|\d{1,2})\s+\d{1,2},?\s*\d{4}\s*[–\-—]+\s*/i, '');
  cleaned = cleaned.replace(/^[A-Z][A-Z\s,]+,\s+\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*[–\-—]+\s*/i, '');
  // Strip date prefix concatenated to content: "16 January 2026F2i..." -> "F2i..."
  cleaned = cleaned.replace(/^\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\s*(?:[|–—-]\s*)?/i, '');
  // Strip "Feb 4,2026|BU news" style prefix
  cleaned = cleaned.replace(/^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s*,\s*\d{4}\s*[|–—-]\s*(?:\w+\s+(?:news|update)\s*)?/i, '');
  // Strip Italian date prefix: "Padova, 22 Dic. 2025" or "Milano, 31 Lug. 2025" (Gradiente SGR artifact)
  cleaned = cleaned.replace(/^(?:[A-ZÀ-Ö][a-zà-ö]+,?\s+)?\d{1,2}\s+(?:Gen|Feb|Mar|Apr|Mag|Giu|Lug|Ago|Set|Ott|Nov|Dic)\.?\s+\d{4}\s*/i, '');
  // Strip sector+date suffixes (Astorg extractor: "...Healthcare29 October 2025" → after spacing → "...Healthcare 29 October 2025")
  cleaned = cleaned.replace(/(?:Healthcare|Tech(?:nology)?|Business\s+Services|Industrials|Financial\s+Services|Consumer|TMT|Energy)\s*\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*$/i, '').trim();
  // Strip date suffixes concatenated to the end: "...in TinextaDecember 30, 2025"
  cleaned = cleaned.replace(/(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{0,4}\s*$/, '').trim();
  // Strip "DD Month YYYY" date suffix at end of title
  cleaned = cleaned.replace(/\s+\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*$/i, '').trim();
  // Strip orphaned trailing 1-2 digit numbers (leftover day from stripped dates)
  cleaned = cleaned.replace(/\s+\d{1,2}\s*$/, '').trim();
  // Strip newspaper attribution suffix ("-- IL SOLE 24 ORE", "-- CORRIERE ECONOMIA", etc.)
  cleaned = cleaned.replace(/\s*[–\-—]+\s*(?:IL SOLE 24 ORE|CORRIERE\s+\w+|BEBEEZ|FORBES|BLOOMBERG|REUTERS|FINANCIAL TIMES|MILANO FINANZA|MF[\s-]MILANO FINANZA|LA REPUBBLICA|ITALIA OGGI|MF NEWSWIRES|STARTUPITALIA)\s*$/i, '');
  // Strip leading/trailing curly quotes (common in Italian news sites)
  cleaned = cleaned.replace(/^[\u201c\u201d"]+\s*/, '').replace(/\s*[\u201c\u201d"]+$/, '');
  // Normalize ALL CAPS titles to title case (3+ consecutive uppercase words)
  if (/^[A-ZÀ-ÖØ-Þ0-9\s.,':;!?()\-–—]+$/.test(cleaned) && cleaned.length > 20) {
    cleaned = cleaned.toLowerCase().replace(/(?:^|\.\s*|[!?]\s*)([a-zà-öø-ÿ])/g, (_, c) => c.toUpperCase())
      .replace(/\b(sgr|spa|srl|sas|eur|ceo|cfo|coo|cio|ipo|pe|vc|esg|aifi|pem|cdp|spac|mbo|lbo|m&a|cda|npl|utp|aum)\b/gi, (m) => m.toUpperCase());
  }
  return cleaned;
}

export function normalizeSignalText(value: string): string {
  return value
    .toLowerCase()
    .replace(/[\u2019'"]/g, '')
    .replace(/[^a-z0-9\u00e0-\u00f9\s]/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function isRedundantSignalSummary(title: string, summary: string): boolean {
  const normTitle = normalizeSignalText(title || '');
  const normSummary = normalizeSignalText(summary || '');
  if (!normTitle || !normSummary) return false;
  if (normTitle === normSummary) return true;
  const shorter = normTitle.length <= normSummary.length ? normTitle : normSummary;
  const longer = normTitle.length <= normSummary.length ? normSummary : normTitle;
  if (shorter.length < 20) return false;
  return longer.includes(shorter);
}

function stripLeadingLabel(text: string): string {
  if (!text) return text;
  // Preserve portfolio and team prefixes — they provide useful context about what happened
  if (/^\s*new\s+(?:portfolio|investment|exit|team\s+member)/i.test(text)) return text;
  return text
    .replace(
      /^\s*(?:news|update|announcement|new announcement|team update|fundraising update|fund close|press release|comunicato stampa|news release)\b\s*(?:[:\-–]|\s+\d|\d)\s*/i,
      ''
    )
    // Strip signal type prefixes — the UI shows type via colored badge
    .replace(
      /^\s*(?:Deal update|Exit update|Fundraise update|Fundraise closing|Fund launch|Debt financing update|People update|Partnership update|Portfolio update|Report update|Hiring update|Update)\s*:\s*/i,
      ''
    )
    .trim();
}

function fixSignalSpacing(text: string): string {
  if (!text) return text;
  let cleaned = text;
  cleaned = cleaned.replace(/(?<=\d)(?=[A-Za-zÀ-ÖØ-öø-ÿ])/g, ' ');
  cleaned = cleaned.replace(/(?<=[A-Za-zÀ-ÖØ-öø-ÿ])(?=\d)/g, ' ');
  cleaned = cleaned.replace(/(?<=[A-ZÀ-ÖØ-Þ]{2})(?=[a-zà-öø-ÿ])/g, ' ');
  cleaned = cleaned.replace(/(?<=[a-zà-öø-ÿ]{3})(?=[A-ZÀ-ÖØ-Þ]{2,})/g, ' ');
  cleaned = cleaned.replace(/([,;:])(?=[A-Za-zÀ-ÖØ-öø-ÿ])/g, '$1 ');
  // Fuse split ordinal suffixes: "28 th" → "28th", "3 rd" → "3rd"
  cleaned = cleaned.replace(/\b(\d+)\s+(st|nd|rd|th)\b/g, '$1$2');
  // Fix missing space after period before uppercase (e.g. "S.p.A.ha" → "S.p.A. ha")
  // but not inside abbreviations like "S.p.A." or "S.r.l."
  cleaned = cleaned.replace(/(\.[A-Za-z]\.)(?=[A-Z][a-z])/g, '$1 ');
  cleaned = cleaned.replace(/(?<=\d),\s+(?=\d)/g, ',');
  const prepositionRegex = /\b(?:di|da|del|dello|della|dei|degli|delle|de|e|ed|la|il|lo|gli|le|al|allo|alla|ai|agli|alle|nel|nello|nella|nei|negli|nelle|sul|sullo|sulla|sui|sugli|sulle|per|con|su|in)/gi;
  const source = cleaned;
  cleaned = cleaned.replace(prepositionRegex, (match, offset) => {
    const nextChar = source[offset + match.length];
    // If the matched text is all-uppercase and followed by uppercase, it's part of
    // an acronym (e.g. "DE" in "DEA", "E" in "EL.MO") — not a preposition to split
    const matchIsAllCaps = match === match.toUpperCase();
    const isAcronym = matchIsAllCaps && nextChar && /[A-ZÀ-ÖØ-Þ]/.test(nextChar);
    if (isAcronym) return match;
    return nextChar && /[A-ZÀ-ÖØ-Þ]/.test(nextChar) ? `${match} ` : match;
  });
  cleaned = cleaned.replace(/(?<=[a-zà-öø-ÿ]{3})(?=[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ])/g, ' ');
  cleaned = cleaned.replace(/\b([A-Za-zÀ-ÖØ-öø-ÿ]{2,})\s([ECIPSV])\s+([a-zà-öø-ÿ]{2,})/g, '$1 $2$3');
  // Restore known names/acronyms broken by digit-letter spacing
  cleaned = cleaned.replace(/\bF\s+2\s+[iI]\b/g, 'F2i');
  cleaned = cleaned.replace(/\bF2I\b/g, 'F2i');
  cleaned = cleaned.replace(/\bB\s+4\s+i\b/g, 'B4i');
  cleaned = cleaned.replace(/\bCO\s+2\b/g, 'CO2');
  cleaned = cleaned.replace(/\b3\s+i\b/g, '3i');
  // Systemic fix: Italian verb forms/words concatenated with preceding words (scraping artifacts)
  // Splits when a recognizable Italian word appears after 3+ lowercase chars mid-token
  // e.g. "Flangesacquisisce" → "Flanges acquisisce", "Motoriinsieme" → "Motori insieme"
  cleaned = cleaned.replace(
    /(?<=[a-zà-öø-ÿ]{3})(acquis(?:isce|iscono|ta\w*|ito|izion[ei])|annuncia\w*|insieme|rafforza\w*|sostenuta|partecipata|accompagnar\w+|controllat[aoi])/gi,
    ' $1'
  );
  // Known name corrections (from CDP VC extractor spacing artifacts)
  cleaned = cleaned.replace(/WS ense/g, 'WSense');
  cleaned = cleaned.replace(/3 DN extech/g, '3DNextech');
  cleaned = cleaned.replace(/T 2 Y Capital/g, 'T2Y Capital');
  cleaned = cleaned.replace(/Visio Ning/g, 'VisiONing');
  cleaned = cleaned.replace(/CAPC orp/g, 'CAPCorp');
  cleaned = cleaned.replace(/job Tech/g, 'jobTech');
  cleaned = cleaned.replace(/Serie Cdi/g, 'Serie C di');
  cleaned = cleaned.replace(/ID e A/g, 'IDeA');
  cleaned = cleaned.replace(/AI 3 D/g, 'AI3D');
  cleaned = cleaned.replace(/Icelake S Acquisition/g, 'Icelakes Acquisition');
  cleaned = cleaned.replace(/De A Capital/g, 'DeA Capital');
  cleaned = cleaned.replace(/B 4 Investimenti/g, 'B4 Investimenti');
  cleaned = cleaned.replace(/Ne Xt RE/g, 'NeXt RE');
  // L Catterton scrape artifact: "LC atterton" → "L Catterton"
  cleaned = cleaned.replace(/LC atterton/g, 'L Catterton');
  // Known name fixes — word-split artifacts (audit H3 + second audit)
  cleaned = cleaned.replace(/\bThe\s+Equity\s+CL\s+ub\b/gi, 'The Equity Club');
  cleaned = cleaned.replace(/\bPintau\s+di\b/g, 'Pintaudi');
  cleaned = cleaned.replace(/\bRobo\s+IT\b/g, 'Robo.IT');
  cleaned = cleaned.replace(/\bSME\s+s\b/g, 'SMEs');
  cleaned = cleaned.replace(/\bB\s+anco\b/g, 'Banco');
  cleaned = cleaned.replace(/\bTGC\s+om\s+24\b/g, 'TGCom24');
  cleaned = cleaned.replace(/\bE\s+4\s+G\b/g, 'E4G');
  cleaned = cleaned.replace(/\bBee\s+2\s+Link\b/g, 'Bee2Link');
  cleaned = cleaned.replace(/\bSmart\s+4\s+T\s*ech\b/g, 'Smart4Tech');
  cleaned = cleaned.replace(/\bAlcedo\s+V\s+and\b/g, 'Alcedo V and');  // preserve as-is: "Alcedo V" is fund gen, "and" is conjunction
  // Additional word-split fixes from second audit
  cleaned = cleaned.replace(/\bT\s+erm\b/g, 'Term');
  cleaned = cleaned.replace(/\bWarste\s+in\b/g, 'Warstein');
  cleaned = cleaned.replace(/\bAAV\s+antgarde\b/g, 'AAVantgarde');
  // Additional known name corrections (digit-letter split artifacts)
  cleaned = cleaned.replace(/\bCY\s*4\s*GATE\b/g, 'CY4GATE');
  cleaned = cleaned.replace(/\bMi\s*CROTEC\b/g, 'MiCROTEC');
  cleaned = cleaned.replace(/\bK\s+3\s*RX\b/g, 'K3RX');
  cleaned = cleaned.replace(/\bB\s+2\s+O\b/g, 'B2O');
  cleaned = cleaned.replace(/\bAI\s+4\s+IV\b/g, 'AI4IV');
  cleaned = cleaned.replace(/\bBIO\s+4\s+DREAMS\b/gi, 'Bio4Dreams');
  // Third audit additions: more word-split artifacts
  cleaned = cleaned.replace(/\bBee\s+2\s+[Ll]ink\b/gi, 'Bee2Link');  // case-insensitive (bee 2 link)
  cleaned = cleaned.replace(/\bB\s+2\s+B\b/g, 'B2B');
  cleaned = cleaned.replace(/\bNeo\s+2\s+A\b/g, 'Neo2A');
  cleaned = cleaned.replace(/\bJob\s+4\s+U\b/g, 'Job4U');
  cleaned = cleaned.replace(/\bEpilepsy\s+GT\s+x\b/g, 'Epilepsy GTx');
  cleaned = cleaned.replace(/\bLV\s+enture\b/g, 'LVenture');
  cleaned = cleaned.replace(/\bInves\s+to\s+Uno\b/g, 'Investo Uno');
  cleaned = cleaned.replace(/\bfinanziamen\s+to\b/gi, 'finanziamento');
  cleaned = cleaned.replace(/\binvestimen\s+to\b/gi, 'investimento');
  cleaned = cleaned.replace(/â¬€/g, '€');  // UTF-8 mojibake for euro sign
  cleaned = cleaned.replace(/\s{2,}/g, ' ');
  return cleaned.trim();
}

const NEWSPAPER_ONLY_RE = /^\s*(?:Il Sole 24 Ore|Corriere\s+\w+|BeBeez|Forbes|Bloomberg|Reuters|Financial Times|Milano Finanza|MF[\s-]Milano Finanza|La Repubblica|Italia Oggi|MF Newswires|StartupItalia|Corriere della Sera)\s*$/i;

export function cleanSignalText(text: string): string {
  if (!text) return text;
  // If entire text is just a newspaper name, clear it
  if (NEWSPAPER_ONLY_RE.test(text)) return '';
  let cleaned = text;
  // Strip [Rumor] prefix — rumor status is conveyed via is_rumor field/badge, not inline text
  cleaned = cleaned.replace(/^\s*\[Rumor\]\s*/i, '');
  // Strip "Featured News Press Review" header (audit H1)
  cleaned = cleaned.replace(/^Featured\s+News\s+Press\s+Review\s*[:\-–]?\s*/i, '');
  // Strip "Media: Milan," or "Media: Rome," press release location headers (audit H2)
  cleaned = cleaned.replace(/^Media\s*:\s*[A-Za-z\u00C0-\u024F]+,?\s+/i, '');
  cleaned = cleaned.replace(/\b\d+\s*min(?:ute)?s?\s*read\b/gi, '');
  cleaned = cleaned.replace(/\b\d+\s*min\.?\s*read\b/gi, '');
  cleaned = cleaned.replace(/\b\d+\s*min(?:uto|uti)\s*di\s*lettura\b/gi, '');
  cleaned = cleaned.replace(/\btempo\s+di\s+lettura\b/gi, '');
  cleaned = cleaned.replace(/\bread\s+time\b/gi, '');
  cleaned = fixSignalSpacing(cleaned);
  cleaned = stripLeadingLabel(cleaned);
  cleaned = fixSignalSpacing(cleaned);
  // Normalize Italian/mixed currency → €XM/€XB format
  cleaned = cleaned.replace(/\boltre\b/gi, 'over');
  cleaned = cleaned.replace(/\bcirca\b/gi, '~');
  cleaned = cleaned.replace(/(\d[\d.,]*)\s*milion[ei]\s+(?:di\s+)?euro/gi, (_, n) => `€${n.replace(',', '.')}M`);
  cleaned = cleaned.replace(/(\d[\d.,]*)\s*miliard[ei]\s+(?:di\s+)?euro/gi, (_, n) => `€${n.replace(',', '.')}B`);
  cleaned = cleaned.replace(/(\d[\d.,]*)\s*mln\s+(?:di\s+)?euros?/gi, (_, n) => `€${n.replace(',', '.')}M`);
  cleaned = cleaned.replace(/(\d[\d.,]*)\s*mld\s+(?:di\s+)?euros?/gi, (_, n) => `€${n.replace(',', '.')}B`);
  // Standalone "mln"/"mld" without explicit currency: in Italian PE, always millions/billions of EUR
  cleaned = cleaned.replace(/(\d[\d.,]*)\s*mln\b(?!\s*(?:azioni|shares?|unit[àa]?))/gi, (_, n) => `€${n.replace(',', '.')}M`);
  cleaned = cleaned.replace(/(\d[\d.,]*)\s*mld\b(?!\s*(?:azioni|shares?|unit[àa]?))/gi, (_, n) => `€${n.replace(',', '.')}B`);
  cleaned = cleaned.replace(/€\s+(\d)/g, '€$1');
  // Strip space + normalize suffix: "€2.9 M" → "€2.9M", "€5 Mn" → "€5M", "€1 Bn" → "€1B", etc.
  cleaned = cleaned.replace(/([€$£]\d[\d.,]*)\s+([MKBT])[a-z]{0,2}\b/g, '$1$2');
  cleaned = cleaned.replace(/\s{2,}/g, ' ').trim();
  // Strip date artifacts appended by enricher (audit C1: 96 signals affected)
  // Pattern: "...announced on 2026-01-15." or "...as of January 15, 2026."
  cleaned = cleaned.replace(/[,.]?\s*(?:announced?|published|reported|observed|noted|dated?|as\s+of)\s+(?:on\s+)?\d{4}-\d{2}-\d{2}\s*\.?\s*$/i, '');
  cleaned = cleaned.replace(/[,.]?\s*(?:announced?|published|reported|observed|noted|dated?|as\s+of)\s+(?:on\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}\s*\.?\s*$/i, '');
  // Also strip orphaned trailing ISO date: "... on 2026-01-15." or " 2026-01-15"
  cleaned = cleaned.replace(/\s+on\s+\d{4}-\d{2}-\d{2}\s*\.?\s*$/i, '');
  cleaned = cleaned.replace(/\s+\d{4}-\d{2}-\d{2}\s*\.?\s*$/i, '');
  // Strip malformed "the is dated" artifacts (audit C1 variant)
  cleaned = cleaned.replace(/\s+the\s+is\s+dated\s+.{0,30}$/i, '');
  // Strip mid-text date artifacts: "announced in a dated YYYY-MM-DD; ..." (audit: equinox-aifm)
  cleaned = cleaned.replace(/,?\s+announced\s+in\s+a\s+dated\s+\d{4}-\d{2}-\d{2}\b[^.]*\./gi, '.');
  cleaned = cleaned.replace(/,?\s+in\s+a\s+dated\s+\d{4}-\d{2}-\d{2}\b[^,.]*/gi, '');
  // Strip mid-text "Media: City, Date –" press release header (audit: faro-value)
  cleaned = cleaned.replace(/\s+Media\s*:\s*\w+,\s+[A-Za-z]+\s+\d{1,2}(?:\s*(?:th|st|nd|rd))?,?\s+\d{4}\s*[–\-—]+\s*/gi, ' ');
  // Strip Italian lead sentence when English translation follows (BeBeez double-language artifact)
  // "Italian text tramite/mediante. English text." → keep only English part
  cleaned = cleaned.replace(/^[^.]{10,250}\b(?:tramite|mediante|che\s+ha|del\s+fondo|nel\s+capitale|al\s+fianco|ha\s+effettuato|ha\s+completato|ha\s+investito|ha\s+chiuso|ha\s+lanciato)\b[^.]*\.\s+(?=[A-Z])/i, '');
  // Strip Italian restatement appended after English summary sentence (audit: ibla-capital)
  // "Fund acquires X. Fund acquisisce X." — remove trailing Italian-language sentence
  cleaned = cleaned.replace(/\.\s+[A-Z][^.]{5,100}\b(?:acquis(?:isce|ta|to)|investe|annuncia|cede|raccoglie|sottoscrive|avvia|rileva)\b[^.]*\.?\s*$/i, '');
  // Strip redundant "New investment involving X" template suffix (audit: gradiente-sgr)
  cleaned = cleaned.replace(/\.\s+New\s+investment\s+involving\s+[^.]{3,80}\.?\s*$/i, '');
  cleaned = cleaned.replace(/\s{2,}/g, ' ').trim();
  // Strip trailing periods — signal text is a headline, not a sentence
  cleaned = cleaned.replace(/\.+\s*$/, '');
  return cleaned;
}

/**
 * Reclassify signal types where the Python classifier got it wrong.
 * Returns corrected signal_type or null to keep original.
 */
export function reclassifySignalType(signal: Signal): SignalType | null {
  // If the enricher ML model confidently overrode the type, trust it — don't re-classify.
  // The enricher applies both universal_demotions and type_corrections before setting this flag.
  const sigAny = signal as any;
  if (sigAny.llm_type_override === true && sigAny.enrichment_confidence === 'high') {
    return null;  // null = keep current type
  }

  const text = ((signal.title || '') + ' ' + (signal.what_changed || '')).toLowerCase();
  const titleText = (signal.title || '').toLowerCase();
  const pageCategory = (signal.page_category || '').toUpperCase();

  // Portfolio company activity → portfolio_update (not fund-level deal)
  if (/\bportfolio\s+compan(?:y|ies)\b/i.test(text) && signal.signal_type !== 'portfolio_update') {
    return 'portfolio_update';
  }
  // "partecipata/sostenuta/backed by" + company action = portfolio company news
  if (/\b(?:partecipata|sostenuta|backed)\b.*\b(?:acquis\w+|complet\w+|espand\w+|expand\w+|rafforz\w+)/i.test(text)) {
    if (signal.signal_type !== 'portfolio_update') return 'portfolio_update';
  }
  // Company revenue/target news → portfolio_update
  if (signal.signal_type === 'other' && /\b(?:ricav\w+|revenue|fatturato)\b.*\b(?:target|milion|mln|€|euro|punta)\b/i.test(text)) {
    return 'portfolio_update';
  }

  // Event/conference attendance → demote (low value, not investment signal)
  if (/\b(?:guest|relator[ei]|speaker|panelist|moderator)\b.*\b(?:evento?|congresso|summit|conferenz|forum|webinar|panel)\b/i.test(text) ||
      /\b(?:evento?|congresso|summit|conferenz|forum|webinar|panel)\b.*\b(?:guest|relator[ei]|speaker|panelist|moderator)\b/i.test(text) ||
      /\binterviene\s+(?:a|al)l['']?\s*(?:event[oi]?|congresso|summit|conferenz\w*|forum|webinar|panel)\b/i.test(text) ||
      /\b(?:partecipa|interviene|presente)\s+(?:a|al)l['']?\s*\w+\s*(?:evento?|congresso|summit|conferenz\w*|forum|webinar|panel|convegno)\b/i.test(text)) {
    return 'website_change';  // website_change signals are filtered out by signals_unified.ts
  }

  // Pure event/conference title → demote (just an event name, no deal content)
  if (/^(?:.*\s)?(?:congress[oi]?|summit|forum|conferenz\w*|convegno|workshop|webinar|tavola\s+rotonda|seminari[oi]?)\s*(?:\d{4}|$)/i.test(text) &&
      !RE_PE_ACTION_VERBS_EXTENDED.test(text)) {
    return 'website_change';
  }

  // Strong exit verbs override all other checks — "Fund cede X" is ALWAYS an exit
  // Added before interview/editorial checks to prevent exit signals from being caught by interview filter
  if (RE_EXIT_VERBS.test(text) && !RE_ACQUISITION_VERBS.test(text)) {
    return 'exit_announced';
  }
  if (/\bsale\s+of\s+(?:its?\s+)?(?:stake|shares?|interest|partecipazione|quota)\b/i.test(text) &&
      !RE_ACQUISITION_VERBS.test(text)) {
    return 'exit_announced';
  }
  if (/\bsuccessful\s+realis\w+\b/i.test(text) && !RE_ACQUISITION_VERBS.test(text)) {
    return 'exit_announced';
  }

  // Interview/editorial without PE transaction verbs → other
  if (/\bintervist\w+\b|\binterview\w*\b|\bevoluzione\s+editoriale\b|\bda\s+settimanale\s+a\b|\bprofile\s+of\b/i.test(text)) {
    if (!RE_PE_ACTION_VERBS.test(text) && !/\b(?:entra\s+nel\s+capitale|vendita|closing)\b/i.test(text)) {
      return 'other';
    }
  }

  // Event insights/recaps → demote (e.g. "Insights from CEO Conference")
  if (/\binsights?\s+from\b.*\b(?:conference|summit|forum|event)\b/i.test(text) ||
      /\b(?:conference|summit|forum)\s+(?:recap|highlights?|takeaways?|wrap[\-\s]?up)\b/i.test(text) ||
      /\bpartner\s+coinvolti\b|\bstartup\s+accelerat\w+\b|\brete\s+nazionale\s+accelerator\w+\b/i.test(text)) {
    return 'other';
  }

  // Marketing/thought-leadership → demote (e.g. "value creation driver")
  // Unconditional — "value creation driver" is marketing framing, never in real deal titles
  if (/\bvalue\s+creation\s+(?:driver|lever|tool|approach)\b/i.test(text)) {
    return 'other';
  }

  // Portfolio company operational articles (tech partnerships, scaling, vendor status — not PE/VC)
  if (/\b(?:solution|technology|platinum|gold|silver)\s+partner\b/i.test(text) ||
      /\bhow\s+\w+\s+is\s+(?:scaling|growing|expanding|transforming)\b/i.test(text) ||
      /\b(?:atlassian|microsoft|salesforce|oracle|sap|aws|azure)\s+(?:partner|solution|marketplace)\b/i.test(text) ||
      /\bmarketplace\s+vendor\b/i.test(text) ||
      /\bscaling\s+across\s+(?:europe|the\s+world|global)\b/i.test(text)) {
    if (!RE_PE_ACTION_VERBS.test(text)) {
      return 'other';
    }
  }

  // Advisory board formation → other (not people_move)
  if (/\b(?:advisory\s+board|comitato\s+(?:scientifico|consultivo))\b/i.test(text) &&
      signal.signal_type === 'people_move' &&
      !/\b(?:appoint\w+|nomin\w+|joins?|entra)\b/i.test(text)) {
    return 'other';
  }

  // Internship/stage offers → job_posting (regardless of current type)
  if (/\b(?:offerta\s+di\s+stage|tirocini[oa]?|stage\s+curriculare)\b/i.test(text)) {
    return 'job_posting';
  }

  // Job posting detection (comprehensive Italian patterns) → job_posting
  // SAFETY NET: Catch job postings that Python ML missed
  if (RE_JOB_SELECTION.test(text)) {
    return 'job_posting';
  }

  // Investor meetings / AGMs → other (not deals)
  // Use strict deal verbs (exclude "invest/investors" as nouns) to avoid false positives
  if (/\binvestor\s+(?:meeting|day|event|conference)\b|\bassemblea\s+(?:dei\s+)?(?:soci|azionisti|investitori)\b|\bagm\b|\bannual\s+general\s+meeting\b/i.test(text)) {
    const STRICT_DEAL_VERBS = /\b(?:acqui(?:res?|sisce|red|sit\w+)|rileva|entra\s+nel\s+capitale|buys?|compra|sells?|sold|exit\w*|cessione|vendita|merger|fusione|ipo\b)\b/i;
    if (!STRICT_DEAL_VERBS.test(text)) {
      return 'other';
    }
  }

  // Pure editorial "investment strategy" / "investment approach" content → other
  if (/\binvestment\s+(?:strategy|approach|philosophy|thesis)\b|\bstrategia\s+d[i'\u2019]\s*investiment[oi]\b|\bour\s+(?:approach|strategy|investment\s+process)\b/i.test(text)) {
    if (!RE_PE_ACTION_VERBS.test(text)) {
      return 'other';
    }
  }

  // Accelerator batch results / graduates → other (not fund launch)
  if (/(?:\b(?:risultati|graduates?|selezionat[ei]|completat[oi]|conclus[oi]|demo\s*day|batch)\b.*\b(?:accelerat\w+|programma)\b|\b(?:accelerat\w+|programma)\b.*\b(?:risultati|graduates?|selezionat[ei]|completat[oi]|conclus[oi]|demo\s*day|batch)\b)/i.test(text)) {
    if (!/\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund)\b/i.test(text)) {
      return 'other';
    }
  }

  // Accelerator/program launches: Python classifies as `other` (filter_signals.py:1311).
  // The TS safety net at lines 754-761 demotes fund_launch→other for accelerators.
  // Do NOT re-promote here — that would override the primary Python gate (M1 audit fix).

  // Italian ownership + bolt-on patterns → portfolio_update
  if (signal.signal_type === 'deal_announced' || signal.signal_type === 'other' || signal.signal_type === 'partnership') {
    if (/\b(?:partecipata|controllata)\s+(?:da|di)\b|\btramite\s+(?:la\s+sua\s+)?(?:partecipata|controllata)\b|\bin\s+portafoglio\s+(?:a|di)\b|\bsociet[àa]\s+in\s+portafoglio\b|\badd[\-\s]?on\b|\bbolt[\-\s]?on\b|\btuck[\-\s]?in\b/i.test(text)) {
      return 'portfolio_update';
    }
  }

  // Portfolio company revenue/performance articles → portfolio_update if evidence, else other
  if (/\bricavi\s+(?:ricorrenti|netti|totali)\b|\brevenue\s+(?:of|growth|reached|exceeds)\b/i.test(text) ||
      /\braggiunge\s+(?:ricavi|fatturato|vendite)\b|\bfatturato\s+(?:di|pari|a)\b/i.test(text) ||
      /\bebitda\s+shortfall\b|\bchiude\s+(?:la\s+)?settimana\s+in\s+(?:calo|rialzo)\b/i.test(text) ||
      /\bal\s+nasdaq\b.*\btitolo\b/i.test(text)) {
    if (!RE_PE_ACTION_VERBS.test(text)) {
      // Check for portfolio company evidence before demoting to other
      if (/\b(?:partecipata|controllata)\s+(?:da|di)\b|\bin\s+portafoglio\b|\bportfolio\s+compan(?:y|ies)\b/i.test(text)) {
        return 'portfolio_update';
      }
      return 'other';
    }
  }

  if (
    (signal.signal_type === 'website_change' || signal.signal_type === 'other') &&
    (pageCategory === 'CAREERS' ||
      /\b(hiring|job|career|position|vacancy|apply|lavora con noi|posizione aperta|recruiting)\b/i.test(text))
  ) {
    return 'job_posting';
  }

  // Financial results/annual report/sustainability report → report
  if (/\b(?:bilancio|financial\s+results?|annual\s+report|year[\-\s]?end\s+report|sustainability\s+report|rapporto\s+(?:annuale|di\s+sostenibilit[àa])|esg\s+report|quarterly\s+(?:report|credit\s+check|results?)|interim\s+report|half[\-\s]?year\s+report|utile\s+d[i'\u2019]\s*esercizio|closes?\s+(?:the\s+)?financial\s+year|risultati?\s+finanziari|utile\s+netto\s+a\s+\d+)\b/i.test(text) ||
      /\b(?:primo|secondo|terzo|quarto)\s+trimestre\b.*\butile\b/i.test(text)) {
    return 'report';
  }

  // Bond issuance / refinancing → debt_financing
  if (/\b(?:bond|obbligazion\w+|emissione|rifinanzia\w+|refinanc\w+|debt\s+issuance|collocamento|collocare?)\b/i.test(text) &&
      !RE_NON_DEBT_VERBS.test(text)) {
    return 'debt_financing';
  }

  // Revolving credit facility → debt_financing
  if (/\brevolving\s+credit\s+facilit\w+\b/i.test(text) ||
      (/\bcredit\s+facilit\w+\b/i.test(text) && /\b(?:upsize|extend|renew)\b/i.test(text))) {
    if (!/\b(?:acqui\w+|investi\w+|rileva)\b/i.test(text)) {
      return 'debt_financing';
    }
  }

  // Broader debt financing: bank loans, private debt, project financing, securitization
  if (/\b(?:private\s+debt\s+(?:transaction|deal|operazion\w+)|project\s+financing|senior\s+(?:secured\s+)?(?:loan|debt|facility|notes?)|mezzanine\s+(?:financ\w+|debt|loan)|unitranche|green\s+bond|debt\s+(?:operation|transaction|facility)|securitiz\w+|cartolarizzazion\w+)\b/i.test(text)) {
    if (!RE_NON_DEBT_VERBS.test(text)) {
      return 'debt_financing';
    }
  }

  // Regulatory/internal dealing communications → other
  if (/\binternal\s+dealing\b|\bcomunicazione\s+(?:internal|interna)\b|\bsoggetto\s+rilevante\s+mar\b|\bregulatory\s+(?:filing|notice|communication)\b|\bandamento\s+(?:titolo|in\s+borsa)\b|\bprocedura\s+di\s+adempimento\b|\blake\s+bidco\b/i.test(text)) {
    return 'other';
  }

  // exit_announced corrections: acquisition/investment verbs → deal_announced
  if (signal.signal_type === 'exit_announced') {
    // Editorial/publication format change (not a PE exit) — e.g. "Grazia evoluzione editoriale"
    if (/\bevoluzione\s+editoriale\b|\bda\s+settimanale\s+a\b|\brivista\b.*\beditoriale\b|\bedizione\s+speciale\b|\bformato\s+editoriale\b/i.test(text)) {
      return 'other';
    }
    const buyerCues = /\bin\s+lizza\b|\bpotrebbe\s+essere\s+interessat\w*\b|\bpotrebbero\s+essere\s+interessat\w*\b|\bvaluta\s+l['\u2019]acqui\w+\b/i;
    const hasExplicitSeller = /\ba\s+vendere\b|\bil\s+venditore\b|\bcede\s+(?:la\s+)?(?:propria\s+)?(?:partecipat\w+|quota|partecipazione)\b|\bcede\s+(?:il\s+)?(?:proprio\s+)?(?:\d+%|controllo|majority|maggioranza)\b|\bdisinvestiment[oi]\b/i.test(text);
    // Buyer-perspective: "in lizza" (bidding), "potrebbe essere interessat" (might be interested) → deal
    if (buyerCues.test(titleText) && !hasExplicitSeller) {
      return 'deal_announced';
    }
    if (buyerCues.test(text) &&
        !/\b(?:sells?|selling|sold|exit\w*|cessione|vendita|vend[eio]\w*|vendut[oa]|cedut[oa]|dismette|a\s+vendere)\b/i.test(text)) {
      return 'deal_announced';
    }
    // Partnership/agreement without PE verbs → partnership
    if (/\b(?:agreement|accordo|intesa|convenzione)\b/i.test(text) &&
        /\b(?:partnership|collaborazione|gestione|manage|management|tenders?|bando)\b/i.test(text) &&
        !/\b(?:sells?|selling|sold|exit\w*|cessione|acquir\w+|investi\w+|rileva)\b/i.test(text)) {
      return 'partnership';
    }
    // "offerta da X mln per" / "offer for" = acquisition bid → deal
    if (/\bofferta\s+(?:da|di|per)\s+\d+|\boffer\s+(?:for|of|to\s+acquire)\b|\bbid\s+(?:for|of|to\s+acquire)\b/i.test(text) &&
        !/\b(?:sells?|selling|sold|exit\w*|cessione|vendita|vend[eio]\w*|vendut[oa]|cedut[oa]|dismette|a\s+vendere)\b/i.test(text)) {
      return 'deal_announced';
    }
    if (/\b(?:acquir\w+|acquis\w+|acquisizion\w+|investi\w+|rileva|entra\s+(?:nel\s+capitale|in)\b|enters?\s+capital|buys?|compra|tratt[ai]\s+l[''\u2019]acquisto|investitore\s+unic\w*\s+al\s+fianco\s+di|sole\s+investor\s+(?:backing|alongside))\b/i.test(text) &&
        !/\b(?:sells?|selling|sold|exit\w*|cessione|vendita|vend[eio]\w*|vendut[oa]|cedut[oa]|dismette|a\s+vendere)\b/i.test(text)) {
      return 'deal_announced';
    }
    // "launch fund" on an exit is wrong → fund_launch
    if (/\b(?:launch|lancia|nasce|nascita|lancio)\b.*\b(?:fund|fondo)\b/i.test(text)) {
      return 'fund_launch';
    }
    // Job posting misclassified as exit (e.g. "procedura di selezione per responsabile")
    if (/\b(?:procedura\s+di\s+selezione|ricerca\s+(?:una?\s+)?risors[ae]|selezione\s+per\s+(?:il\s+)?(?:ruolo|responsabile|posizione)|avvia\s+(?:la\s+)?selezione|seeks?\s+a\s+(?:full|part)[\-\s]time)\b/i.test(text)) {
      return 'job_posting';
    }
    // Safety net: exit_announced with ZERO PE-related verbs → other
    // Real exits always mention selling, exiting, or deal-related language
    if (pageCategory !== 'PORTFOLIO' &&
        !/\b(?:sells?|selling|sold|exit\w*|cessione|vendita|vend[eio]\w*|vendut[oa]|cedut[oa]|dismette|a\s+vendere|acquir\w+|acquisizion\w*|investi\w+|rileva|entra\s+nel\s+capitale|enters?\s+capital|buys?|compra|offerta\b|offer\b|bid\b|fundrais\w+|raccolta|closing|round|series|seed|chiude|chiusura|launch|lancia|nasce|nascita|lancio|partnership|joint\s+venture|nomina|appointed|ipo\b|merger|fusione|buyout|lbo\b|takeover|finanziamento|aumento\s+di\s+capitale|operazione|finalizzat\w+)\b/i.test(text)) {
      return 'other';
    }
  }

  // fund_launch false positives: "Xth investimento per Fund N" → deal
  if (signal.signal_type === 'fund_launch') {
    // Accelerator/program launch → other (strategic initiative, not a fund vehicle)
    // Only reclassify if it's NOT also a genuine fund launch (e.g. "lancia fondo + acceleratore")
    if (/(?:\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new|al\s+via)\b.*\b(?:accelerat\w*|polo|programma|hub)\b|\b(?:accelerat\w*|polo|programma|hub)\b.*\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?)\b)/i.test(text)) {
      if (!/\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund|comparto|veicolo|vehicle)\b/i.test(text) &&
          !/\b(?:fund|fondo)\s+(?:i{1,3}|iv|v|vi{1,3}|ix|x|\d+)\b/i.test(text) &&
          !/\b(?:new\s+fund|nuovo\s+fondo|fund\s+formation|vehicle\s+launch|fund\s+(?:launch|inception|creation))\b/i.test(text)) {
        return 'other';
      }
    }
    // Accelerator batch results / graduates → other (not a fund launch)
    // e.g. "5 startup selezionate dall'acceleratore", "risultati del programma di accelerazione"
    if (/(?:\b(?:risultati|graduates?|selezionat[ei]|completat[oi]|conclus[oi]|demo\s*day|batch)\b.*\b(?:accelerat\w+|programma)\b|\b(?:accelerat\w+|programma)\b.*\b(?:risultati|graduates?|selezionat[ei]|completat[oi]|conclus[oi]|demo\s*day|batch)\b)/i.test(text)) {
      if (!/\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund)\b/i.test(text)) {
        return 'other';
      }
    }
    // Outsourcing/procurement notices → other (not a deal or fund launch)
    if (/\b(?:outsourcing|affidamento\s+in\s+outsourcing|indagine\s+esplorativa|manifestazion[ei]\s+di\s+interesse|procedura\s+comparativa|gara\s+d[i'\u2019]\s*appalto|bando\s+di\s+gara)\b/i.test(text)) {
      return 'other';
    }
    // Job posting language → job_posting
    if (/\b(?:procedura\s+di\s+selezione|ricerca\s+(?:una?\s+)?risors[ae]|selezione\s+per\s+(?:il\s+)?(?:ruolo|responsabile|posizione)|avvia\s+(?:la\s+)?selezione)\b/i.test(text)) {
      return 'job_posting';
    }
    // Ordinal investment for existing fund → deal (Italian + English ordinals)
    if (/\b(?:nuovo|nuov[oa]|primo|secondo|terz[oa]|quart[oa]|quint[oa]|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+[°ºª]?)\s+(?:investiment[oi]|investment|operazione|operation)\b/i.test(text)) {
      return 'deal_announced';
    }
    // "takes a stake in X" / "preso quota in X" = acquisition language → deal
    if (/\btakes?\s+(?:a\s+)?(?:stake|quota|partecipazione)\b|\bpreso\s+(?:una?\s+)?(?:quota|partecipazione)\b/i.test(text)) {
      return 'deal_announced';
    }
    // Board/appointment language → people_move
    if ((/\b(?:board|consiglio|nomina|appointed|eletto|nuovo\s+(?:cda|consiglio))\b/i.test(text) || /\bnew\s+(?:head|director|managing\s+director)\b/i.test(text) || /\bstrengthens?\b.*\bteam\b/i.test(text)) &&
        !/\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund|comparto|veicolo|vehicle)\b/i.test(text)) {
      return 'people_move';
    }
    // Office opening / footprint expansion → people_move
    if (/\bopens?\s+(?:a\s+|an\s+|new\s+)?(?:\w+\s+){0,3}office\b|\bapre\s+(?:un\s+)?(?:nuovo\s+)?ufficio\b/i.test(text) &&
        !/\b(?:acqui\w+|investi\w+|rileva)\b/i.test(text)) {
      return 'people_move';
    }
    if (/\b(?:partnership|partners?\s+with|joint\s+venture|jv\b|distribution\s+agreement|strategic\s+alliance|collaborazione\s+strategica|accordo\s+(?:di\s+)?(?:collaborazione|distribuzione|partnership)|alleanza\s+strategica|intesa\s+(?:strategica|commerciale))\b/i.test(text) &&
        !/\b(?:acqui\w+|rileva|buyout|majority|minority\s+stake|entra\s+nel\s+capitale)\b/i.test(text)) {
      return 'partnership';
    }
    // "offerta da X mln" = acquisition bid → deal
    if (/\bofferta\s+(?:da|di|per)\s+\d+|\boffer\s+(?:for|of|to\s+acquire)\b|\bbid\s+(?:for|of)\b/i.test(text)) {
      return 'deal_announced';
    }
    // Project financing → debt_financing
    if (/\bproject\s+financing\b|\briceve\s+finanziamento\b|\bsottoscritto\s+(?:project\s+)?financ\w+\b/i.test(text)) {
      return 'debt_financing';
    }
    if (/\b(?:acquisizion\w*|acquis[it]\w+|investi(?:ment|sce|to)|rileva|entra (?:nel capitale|in)|acqui(?:res?|sisce|red)|compra|buyout|operazione|finalizzat\w+|investitore\s+unic\w*\s+al\s+fianco\s+di|sole\s+investor\s+(?:backing|alongside))\b/i.test(text)) {
      return 'deal_announced';
    }
    if (/\b(?:exit|divest\w+|sells?|sold|cessione|vendita|vend(?:e|ere|ono)|vendut[oa])\b/i.test(text)) {
      return 'exit_announced';
    }
    // "surpasses X in capital" / "arriva a X mln" → fundraise
    if (/\bsupera\s+(?:i\s+)?\d+.*(?:raccolt|capital)\b|\bsupera(?:ndo)?\s+(?:il\s+)?(?:proprio\s+)?target\b|\bsurpass\w*\s+\d+.*(?:raised|capital)\b|\bsurpass(?:ing)?\s+(?:its?\s+)?target\b|\barriva\s+a\s+\d+.*\b(?:m|mln|milion)\b/i.test(text)) {
      return 'fundraise_closed';
    }
    // "chiude il fondo" or "chiusura fondo" → fundraise_closed
    if (/\bchiude\b.*\b(?:fondo|fund)\b|\bchiusura\b.*\b(?:fondo|fund)\b/i.test(text)) {
      return 'fundraise_closed';
    }
    // Debt restructuring → other (not fund launch)
    if (/\baccordo\s+(?:tra|con)\s+(?:il\s+)?(?:i\s+)?creditor\w*\b|\baccordo\s+di\s+ristrutturazione\b|\bconcordato\b/i.test(text) &&
        !/\b(?:acqui\w+|investi\w+|rileva)\b/i.test(text)) {
      return 'other';
    }
    // Safety net: fund_launch with NO actual fund launch language → other
    // Catches ML putting "fund_launch" on editorial content
    // NOTE: accelerat*/polo removed — accelerator launches are caught above and returned as 'other'
    if (!/\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund|comparto|veicolo|vehicle)\b/i.test(text) &&
        !/\b(?:fund|fondo)\s+(?:i|ii|iii|iv|v|vi|vii|viii|\d+)\b/i.test(text) &&
        !/\b(?:new\s+fund|nuovo\s+fondo|fund\s+formation|vehicle\s+launch|fund\s+(?:launch|inception|creation))\b/i.test(text) &&
        !/\boperativ[oa]\s+(?:il\s+)?comparto\b/i.test(text)) {
      return 'other';
    }
  }

  // fundraise_announced corrections: acquisition verbs → deal, closing verbs → fundraise_closed
  if (signal.signal_type === 'fundraise_announced') {
    if (/\b(?:rileva|entra (?:nel capitale|in)|acquisizion\w*|acquisisce|acquir\w+|compra)\b/i.test(text)) {
      return 'deal_announced';
    }
    if (/\bchiuso il closing\b|\bchius[oa]\b.*\bclosing\b|\bfinal close\b|\bhard cap\b|\b(?:primo|secondo|terzo|first|second|third|successful)\s+closing\b|\bclosing\s+(?:del|di|per|of)\s+(?:il\s+)?(?:fondo|fund|veicolo|oversubscribed)\b/i.test(text)) {
      return 'fundraise_closed';
    }
    // "closing of oversubscribed" / "announces closing" → fundraise_closed
    if (/\bclosing\s+of\s+(?:oversubscribed|the)\b|\bannounces\s+closing\b/i.test(text)) {
      return 'fundraise_closed';
    }
    if (/\bsupera(?:ndo)?\s+(?:il\s+)?(?:proprio\s+)?target\b|\bsurpass(?:ing)?\s+(?:its?\s+)?target\b/i.test(text)) {
      return 'fundraise_closed';
    }
    if (/\b(?:lancia|lancio|nasce|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund)\b/i.test(text)) {
      return 'fund_launch';
    }
    // Portfolio company debt financing → debt_financing (not fund fundraise)
    if (/\b(?:bond|obbligazion\w+|rifinanzia\w+|refinanc\w+|project\s+financing|private\s+debt\s+transaction)\b/i.test(text) &&
        !/\b(?:primo|secondo|terzo|final[e]?)\s+closing\b/i.test(text)) {
      return 'debt_financing';
    }
  }
  // Portfolio company rounds: fundraise → deal_announced
  // When a fund's portfolio company raises a round, it's the fund's investment (not a fund-level fundraise)
  if (signal.signal_type === 'fundraise_announced' || signal.signal_type === 'fundraise_closed') {
    // Check for company-level round patterns
    const hasCompanyRound = (
      /\b(?:round|serie|series|seed|pre[-\s]?seed)\s+(?:a|b|c|d|e|f|di)\b/i.test(text) ||
      /\bserie\s+[a-f]\b/i.test(text) ||
      /\bround\s+(?:seed|pre[-\s]?seed)\b/i.test(text) ||
      /\bround\s+(?:d[i'\u2019]\s*)?(?:investimento|finanziamento)\b/i.test(text) ||
      /\bround\s+da\s+\d+/i.test(text) ||
      /\bincassa\s+(?:nuovo\s+)?round\b/i.test(text) ||
      /\braccog\w+\s+\d+\s*(?:m|mln|milion|k|mila)\b/i.test(text) ||
      /\baumento\s+di\s+capitale\b.*\bstartup\b/i.test(text) ||
      /\bstartup\b.*\baumento\s+di\s+capitale\b/i.test(text) ||
      /\bchiude\s+un\s+(?:round|aumento\s+di\s+capitale)\b/i.test(text) ||
      /\briceve\s+un\s+finanziamento\b/i.test(text) ||
      /\baumento\s+di\s+capitale\s+(?:con|sottoscritto\s+da|da)\s+\w+/i.test(text) ||
      /\b(?:startup|scaleup|scale-up|spin[-\s]?off)\b.*\b(?:chiude|raccog\w+|riceve|incassa|ottiene|conclude|completa)\b/i.test(text) ||
      /\b(?:chiude|raccog\w+|riceve|incassa|ottiene|conclude|completa)\b.*\b(?:startup|scaleup|scale-up|spin[-\s]?off)\b/i.test(text) ||
      /\bfinanziamento\s+da\s+\d+/i.test(text) ||
      /\bottiene\s+un\s+finanziamento\b/i.test(text) ||
      /\b(?:completa|conclude)\s+(?:un\s+)?(?:round|aumento\s+di\s+capitale)\b/i.test(text) ||
      /\bporta\s+a\s+casa\s+(?:un\s+)?round\b/i.test(text) ||
      /\b(?:chiuso|completato|concluso)\s+(?:il\s+)?(?:round|aumento\s+di\s+capitale)\b/i.test(text) ||
      /\b\d+(?:[.,]\d+)?\s*(?:milion\w*|mln|mila)\s+di\s+euro\s+di\s+raccolta\b/i.test(text) ||
      // English patterns for translated startup rounds
      /\b(?:closed?s?|completes?|secures?|raises?)\s+(?:a\s+)?[€$£]?\s*[\d.,]+\s*(?:M|m|mln|million|B|bn|billion)?\s*(?:round|funding)\b/i.test(text) ||
      /\b[€$£]\s*[\d.,]+\s*(?:M|m|mln|million|B|bn|billion)\s+(?:round|funding)\s+(?:led|backed|from)\b/i.test(text) ||
      /\bstartup\b.*\b(?:closed?s?|raised?s?|secures?|completes?)\b.*\b(?:round|funding)\b/i.test(text)
    );
    // Exclude fund-level fundraise (the fund itself raising capital from LPs)
    const isFundLevelFundraise = /\b(?:primo|secondo|terzo|final[e]?)\s+closing\s+(?:del|di|per)\s+(?:il\s+)?(?:fondo|fund|veicolo)\b/i.test(text) ||
      /\bclosing\s+(?:del|di|per|of)\s+(?:il\s+)?(?:fondo|fund|veicolo)\b/i.test(text) ||
      /\btarget\s+size\b/i.test(text) ||
      /\bhard\s+cap\b/i.test(text) ||
      /\braccolta\s+(?:del|di|per)\s+(?:il\s+)?(?:fondo|fund)\b/i.test(text) ||
      /\braccog\w+.*\b(?:per|for)\s+(?:il\s+proprio\s+|its?\s+own\s+)?(?:fondo|fund)\b/i.test(text) ||
      /\bcommitted?\s+capital\b/i.test(text) ||
      /\bfund\s+(?:i{1,3}|iv|v|vi{1,3}|ix|x|\d+)\s+(?:at|a|di)\s+/i.test(text) ||
      /\boversubscribed\b/i.test(text);
    if (hasCompanyRound && !isFundLevelFundraise) {
      return 'deal_announced';
    }
  }
  // "Chiude la raccolta a X" → fundraise_closed
  if (signal.signal_type === 'fund_launch' || signal.signal_type === 'fundraise_announced' || signal.signal_type === 'deal_announced') {
    if (/\bchiude\s+la\s+raccolta\b|\bchiude\b.*\bfundraising\b|\bcloses\s+fundraising\b/i.test(text)) {
      return 'fundraise_closed';
    }
  }
  if (signal.signal_type === 'deal_announced') {
    // "exited from portfolio" / "uscita dal portafoglio" → exit, not deal
    if (/\b(?:exited?\s+from\s+.*portfolio|uscit[ao]\s+dal?\s+portafoglio)\b/i.test(text)) {
      return 'exit_announced';
    }
    // Strong exit verbs in deal signal → exit (e.g. "Permira exits Golden Goose",
    // "Successful Realisation Of Investment", "sale of its stake")
    if (/\b(?:sells?|sold|vend(?:e|ere|ita|ono)|vendut[oa]|cede|cession[ei]|disinvest\w+|divest\w+|exits?|exited|realis(?:ation|ed)|realiz(?:ation|ed))\b/i.test(text) &&
        !/\b(?:acquir\w+|acquisizion\w+|rileva|buys?|compra)\b/i.test(text)) {
      return 'exit_announced';
    }
    if (/\bsale\s+of\s+(?:its?\s+)?(?:stake|shares?|interest|partecipazione|quota)\b/i.test(text) &&
        !/\b(?:acquir\w+|acquisizion\w+|rileva|buys?|compra)\b/i.test(text)) {
      return 'exit_announced';
    }
    if (/\bsuccessful\s+realis\w+\b/i.test(text) &&
        !/\b(?:acquir\w+|acquisizion\w+|rileva|buys?|compra)\b/i.test(text)) {
      return 'exit_announced';
    }
    // Outsourcing/procurement → other (not a deal)
    if (/\b(?:outsourcing|affidamento\s+in\s+outsourcing|indagine\s+esplorativa|manifestazion[ei]\s+di\s+interesse|procedura\s+comparativa|gara\s+d[i'\u2019]\s*appalto|bando\s+di\s+gara)\b/i.test(text)) {
      return 'other';
    }
    // Internship offer → job_posting (not deal)
    if (/\b(?:offerta\s+di\s+stage|tirocini[oa]?|stage\s+curriculare)\b/i.test(text)) {
      return 'job_posting';
    }
    // Job posting language → job_posting
    if (/\b(?:procedura\s+di\s+selezione|ricerca\s+(?:una?\s+)?risors[ae]|selezione\s+per\s+(?:il\s+)?(?:ruolo|responsabile|posizione)|avvia\s+(?:la\s+)?selezione)\b/i.test(text)) {
      return 'job_posting';
    }
    // "Strengthens team" / "senior appointments" → people_move
    if (/\bstrengthens?\b.*\bteam\b|\bsenior\s+appointments?\b/i.test(text) &&
        !/\b(?:acqui\w+|investi\w+|rileva|buyout)\b/i.test(text)) {
      return 'people_move';
    }
    // Partnership signals → partnership
    if (/\b(?:partnership|partners?\s+(?:with|to\s+deliver)|joint\s+venture|distribution\s+agreement|accordo\s+(?:di\s+)?(?:collaborazione|distribuzione|partnership)|alleanza\s+strategica|intesa\s+(?:strategica|commerciale))\b/i.test(text) &&
        !/\b(?:acqui\w+|rileva|buyout|majority|minority\s+stake|entra\s+nel\s+capitale)\b/i.test(text)) {
      return 'partnership';
    }
    // Fund itself acquired by another entity → other (corporate M&A of PE firm)
    if (/\b(?:acquisition|acquisizione)\s+(?:by|da\s+parte\s+di)\b/i.test(text)) {
      return 'other';
    }
    // Concordato/restructuring → other
    if (/\bconcordato\b|\brestructuring\s+agreement\b/i.test(text) &&
        !/\b(?:acqui\w+|investi\w+|rileva)\b/i.test(text)) {
      return 'other';
    }
    // Bond/debt financing misclassified as deal
    if (/\b(?:bond|obbligazion\w+|emissione|rifinanzia\w+|refinanc\w+|debt\s+issuance|collocamento)\b/i.test(text) &&
        !/\b(?:acqui\w+|rileva|investiment[oi]|exit|sells?|cessione|launch|lancia|nasce)\b/i.test(text)) {
      return 'debt_financing';
    }
    // Fundraise closing misclassified as deal
    if (/\bclosing\s+(?:del|di|per|of)\s+(?:il\s+)?(?:fondo|fund|oversubscribed)\b/i.test(text)) {
      return 'fundraise_closed';
    }
    // Fundraise round misclassified as deal
    if (/\braccog\w+\b.*\b(?:milion|mln|m€|round|seed|serie|series)\b/i.test(text) &&
        !/\b(?:acquis\w*|rileva|entra nel capitale)\b/i.test(text)) {
      return 'fundraise_announced';
    }
    if (/\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund|comparto|veicolo|vehicle)\b/i.test(text)) {
      return 'fund_launch';
    }
  }

  // people_move safety net: people_move with NO people-related language → other
  if (signal.signal_type === 'people_move') {
    if (!/\b(?:appoint\w+|joins?|joined|nomin(?:a|e|at\w+)|named?\s+(?:as\s+)?(?:ceo|cfo|coo|cio|partner|director|head|president|chairman)|promot\w+|hired?|board|consiglio|eletto|assume\s+(?:il\s+)?(?:ruolo|incarico)|entra\s+(?:nel\s+)?(?:team|consiglio|cda)|nuovo\s+(?:ingresso|membro)|new\s+(?:head|director|managing\s+director|president|chairman))\b/i.test(text) && !/\bstrengthens?\b.*\bteam\b/i.test(text)) {
      return 'other';
    }
  }

  // Partnership patterns (check before deal patterns to avoid misclassification)
  // These are business partnerships, JVs, distribution agreements — not acquisitions
  // Accelerator/program launches are NOT partnerships even if they have "partnership" language
  if (signal.signal_type === 'deal_announced' || signal.signal_type === 'other' || signal.signal_type === 'website_change') {
    if (/\b(?:partnership|partners?\s+(?:with|to\s+deliver)|joint\s+venture|jv\b|distribution\s+agreement|strategic\s+alliance|collaborazione\s+strategica|accordo\s+(?:di\s+)?(?:collaborazione|distribuzione|partnership)|alleanza\s+strategica|intesa\s+(?:strategica|commerciale))\b/i.test(text) &&
        !/\b(?:acqui\w+|rileva|buyout|majority|minority\s+stake|entra\s+nel\s+capitale)\b/i.test(text) &&
        !(/(?:\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new|al\s+via)\b.*\b(?:accelerat\w*|polo|programma|hub)\b|\b(?:accelerat\w*|polo|programma|hub)\b.*\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?)\b)/i.test(text))) {
      return 'partnership';
    }
  }

  // Reclassify "other" signals using keyword patterns (defense-in-depth)
  if (signal.signal_type === 'other' || signal.signal_type === 'website_change') {
    // Outsourcing/procurement → stay other (not a deal)
    if (/\b(?:outsourcing|affidamento\s+in\s+outsourcing|indagine\s+esplorativa|manifestazion[ei]\s+di\s+interesse|procedura\s+comparativa|gara\s+d[i'\u2019]\s*appalto|bando\s+di\s+gara)\b/i.test(text)) {
      return 'other';
    }
    // Job posting patterns
    if (/\b(?:procedura\s+di\s+selezione|ricerca\s+(?:una?\s+)?risors[ae]|selezione\s+per\s+(?:il\s+)?(?:ruolo|responsabile|posizione)|avvia\s+(?:la\s+)?selezione|seeks?\s+a\s+(?:full|part)[\-\s]time)\b/i.test(text)) {
      return 'job_posting';
    }
    // Exit patterns (check first) — includes strong exit verbs
    if (/\b(?:exits?|exited|divest\w+|sells?|selling|sold|sale|cessione|cede|cession[ei]|cedut[oa]|vendita|vende|vendut[oa]|uscita|dismette|disinvest\w+|a\s+vendere|realis(?:ation|ed)|realiz(?:ation|ed))\b/i.test(text) ||
        /\bsale\s+of\s+(?:its?\s+)?(?:stake|shares?|interest|partecipazione|quota)\b/i.test(text) ||
        /\bsuccessful\s+realis\w+\b/i.test(text)) {
      return 'exit_announced';
    }
    // Debt financing patterns (check before deal — debt is NOT equity)
    if (/\b(?:bond|obbligazion\w+|emissione|rifinanzia\w+|refinanc\w+|debt\s+issuance|collocamento)\b/i.test(text) &&
        !/\b(?:acqui\w+|rileva|investiment[oi]|exit|sells?|cessione|launch|lancia|nasce)\b/i.test(text)) {
      return 'debt_financing';
    }
    if (/\b(?:project\s+financing|private\s+debt\s+(?:transaction|deal)|senior\s+(?:secured\s+)?(?:loan|notes?)|mezzanine|unitranche|green\s+bond|securitiz\w+|debt\s+(?:operation|deployment|facility))\b/i.test(text) &&
        !/\b(?:acqui\w+|rileva|investiment[oi]|exit|sells?|cessione|launch|lancia|nasce)\b/i.test(text)) {
      return 'debt_financing';
    }
    // M&A talks / negotiations — even when a deal falls through it is deal news
    if (/\btrattative\s+(?:di\s+(?:acqui\w+|vendita|cessione)|per\s+l[a'\u2019]\s*acqui\w+)\b|\b(?:halt|stop|end|cessazione)\s+(?:to\s+|of\s+|alle?\s+)?(?:acquisition|deal|merger|trattative)\s*(?:talks?|discussions?|negoti\w*)?\b|\bacquisition\s+talks?\b|\bM&A\s+talks?\b|\bnegotiations?\s+(?:for|to)\s+(?:acqui\w+|merger\w*)\b/i.test(text)) {
      return 'deal_announced';
    }
    // Deal patterns (partnership already handled above)
    if (/\b(?:acqui\w+|investiment[oi]\s+da\s|investe\b|entra nel capitale|enters?\b.*\bcapital|rileva|stake|majority|minority|buyout|partecipazione|operazione|finalizzat\w+|concessi\w+|sostiene|secures?\s+(?:€|\$|£)?\s*\d+|secur(?:es?|ing)\b.{0,40}\b(?:investment|funding|financing)\b|series\s+[a-g]\b|(?:seed|pre-seed)\s+(?:round|funding)|funding\s+round|(?:€|\$|£)\s*\d+\s*(?:m(?:illion|ln)?|b(?:illion|n)?)\s+(?:round|investment|funding)|investitore\s+unic\w*\s+al\s+fianco\s+di|sole\s+investor\s+(?:backing|alongside))\b/i.test(text)) {
      return 'deal_announced';
    }
    // Fund launch patterns (strictly fund vehicles, NOT accelerators/programs)
    if (/\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund|comparto|veicolo|vehicle)\b/i.test(text)) {
      return 'fund_launch';
    }
    // Fundraise patterns (including credit facility/upsize)
    if (/\b(?:fundrais\w+|first close|first closing|final close|primo closing|closing\b.*\b(?:million|mln|milion|€|eur)|raccog\w+|raccolta|chiusura|chiude|(?:revolving\s+)?credit\s+facilit(?:y|ies)|upsize[sd]?)\b/i.test(text)) {
      if (/\b(?:final close|hard cap|closed|chiude|chius[oa]|complet\w+)\b/i.test(text)) {
        return 'fundraise_closed';
      }
      return 'fundraise_announced';
    }
    // People move patterns
    if (/\b(?:appoint\w+|joins?|joined|nomin(?:a|e|at\w+)|named?\s+(?:as\s+)?(?:ceo|cfo|coo|cio|partner|director|head|president|chairman)|names\b.*\b(?:as\s+)?(?:incoming\s+)?(?:head|chief|officer|partner|director|managing|president|chairman)|new\s+(?:head|director|managing\s+director|president|chairman))\b/i.test(text) || /\bstrengthens?\b.*\bteam\b/i.test(text)) {
      return 'people_move';
    }
  }

  return null;
}
