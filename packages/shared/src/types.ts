/**
 * Fundradar shared types
 * Reliability contract: every Signal must have source_url + observed_at + what_changed
 */

export type DataSource =
  | 'fund_website'   // Tier 1 – fund's own website
  | 'linkedin'       // Tier 2 – LinkedIn profiles/pages
  | 'aifi'           // Tier 3 – AIFI association
  | 'pem'            // Tier 4 – PEM deal reports (historical, OCR)
  | 'news'           // Tier 5 – third-party news (may be unverified)
  | 'manual';        // Tier 6 – hand-entered or AI-generated seed data

/**
 * Fund/Entity category taxonomy
 * Canonical categories for PE/VC funds and related entities
 */
export type FundCategory =
  | 'pe'            // Private Equity (buyout)
  | 'vc'            // Venture Capital
  | 'growth'        // Growth Equity
  | 'infra'         // Infrastructure
  | 'debt'          // Private Debt / Credit
  | 'real_estate'   // Real Estate
  | 'holdings'      // Holding company / Family office
  | 'fund_of_funds' // Fund of Funds
  | 'multi_strategy'// Multi-strategy (PE + Credit + Infra etc.)
  | 'sovereign'     // Sovereign wealth fund / Development bank
  | 'bank'          // Banking institution
  | 'asset_manager' // Traditional asset manager
  | 'unknown';      // Not yet classified

export const FUND_CATEGORY_LABELS: Record<FundCategory, string> = {
  pe: 'Private Equity',
  vc: 'Venture Capital',
  growth: 'Growth Equity',
  infra: 'Infrastructure',
  debt: 'Private Debt',
  real_estate: 'Real Estate',
  holdings: 'Holdings',
  fund_of_funds: 'Fund of Funds',
  multi_strategy: 'Multi-Strategy',
  sovereign: 'Sovereign',
  bank: 'Bank',
  asset_manager: 'Asset Manager',
  unknown: 'Unknown',
};

export interface Office {
  city: string;
  country: string;
  address?: string | null;
  postal_code?: string | null;
  phone?: string | null;
  lat?: number | null;
  lng?: number | null;
  is_hq: boolean;
  is_italy: boolean;
  source_url?: string | null;   // e.g. "https://www.towerbrook.com/contact"
  source_name?: string | null;  // e.g. "Fund Website"
}

export interface Fund {
  id: string;
  slug: string;
  name: string;
  category: FundCategory;
  canonical_id?: string;        // Points to canonical entity if this is an alias
  aliases?: string[];           // List of alias names for this canonical entity
  hq_city: string | null;
  hq_region: string | null;
  hq_address?: string | null;
  hq_lat?: number | null;
  hq_lng?: number | null;
  offices?: Office[];
  website: string | null;
  strategy_tags: string[];      // Investment focus (e.g., "Buy Out", "Early Stage")
  sector_tags: string[];        // Industry sectors (e.g., "Healthcare", "Industrial")
  description: string | null;
  // AIFI extended fields for filtering
  geographies?: string[];       // Target geographies (e.g., "Italy", "Europe")
  average_investment?: string[]; // Investment size ranges (e.g., "€1-5m", "€5-20m")
  asset_class?: string[];       // Asset class (e.g., "Private Equity", "Venture Capital")
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;

  // AIFI metrics (optional, from AIFI scraper)
  aum_eur?: number | null;
  num_funds?: number | null;
  num_portfolio_companies?: number | null;
  num_executives?: number | null;
  num_sfdr_article_8?: number | null;
  investment_min_eur?: number | null;
  investment_max_eur?: number | null;
  linkedin_url?: string | null;
  aifi_url?: string | null;
  aifi_scraped_at?: string | null;
  data_sources?: string[];       // Source URLs for AI/manual-enriched fields
  data_confidence?: string | null;

  created_at: string;
  updated_at: string;
}

/**
 * Signal type enum. When adding a new type, update ALL of these files:
 *
 * 1. HERE — add to the union type below
 * 2. apps/web/src/lib/signalProcessing.ts — SIGNAL_TYPE_STYLES (badge label/color/importance)
 * 3. apps/web/src/app/signals/SignalsFeed.tsx — filter chip in SIGNAL_TYPE_FILTERS import
 * 4. apps/worker/scripts/filter_signals.py — TYPE_SCORES, CORE_GEO_TYPES/CORE_QUALITY_TYPES
 * 5. apps/worker/scripts/enrich_signals_openai.py — LLM_EVENT_TYPE_MAP, _signal_type_prefix()
 * 6. apps/worker/scripts/signal_patterns.py — CORE_GEO_TYPES, CORE_QUALITY_TYPES (if core)
 */
export type SignalType =
  | 'fundraise_announced'
  | 'fundraise_closed'
  | 'fund_launch'
  | 'deal_announced'
  | 'exit_announced'
  | 'debt_financing'
  | 'report'
  | 'partnership'
  | 'people_move'
  | 'job_posting'
  | 'portfolio_update'
  | 'website_change'
  | 'other';

export type SourceUrlStatus = 'ok' | 'unavailable' | 'unknown';

/**
 * Signal: a publicly observed event with full provenance
 * RELIABILITY: source_url and observed_at are required, never infer claims
 */
export interface Signal {
  id: string;
  fund_id: string;
  fund_slug?: string;
  signal_type: SignalType;
  title: string;
  what_changed: string;
  source_url: string;
  source_name: string;
  source_url_status?: SourceUrlStatus;
  source_url_checked_at?: string;
  published_at: string | null;
  observed_at: string;
  created_at: string;
  page_category?: string;
  extraction_source?: string;
  // Data provenance (added for source hierarchy)
  data_source?: DataSource;
  verified?: boolean;             // false for news/rumor signals
  is_rumor?: boolean;             // true for unconfirmed deals, negotiations, rumors
  enriched_summary_original?: string;  // original Italian text (before translation)
  title_original?: string;             // original Italian title (before translation)
  what_changed_original?: string;      // original Italian what_changed (before translation)
}

/**
 * Deal: a PE/VC investment extracted from PEM data
 * Provenance: source_file and source_year track where this data came from
 */
export interface Deal {
  id: string;
  target_company: string;
  lead_investor: string;
  lead_investor_slug: string;
  co_investors: string[] | null;
  invested_amount_eur_mln: number | null;
  acquired_stake_pct: number | null;
  investment_stage: string | null;
  deal_origination: string | null;
  region: string | null;
  sector: string | null;
  sector_detail: string | null;
  source_file: string;
  source_year: number;
}

export interface PemManifestEntry {
  filename: string;
  year_inferred: number | null;
  sha256: string;
  path: string;
}

export interface PemManifest {
  generated_at: string;
  entries: PemManifestEntry[];
}

/**
 * LinkedIn Team Analytics
 * Aggregated stats from LinkedIn employee profiles
 */
export interface TeamEducation {
  top_schools: Record<string, number>;
  top_degrees: Record<string, number>;
  top_majors: Record<string, number>;
  education_tier: {
    top_mba: number;
    top_undergrad: number;
    other: number;
  };
}

export interface TeamAnalytics {
  fund_slug: string;
  total_profiles: number;
  education: TeamEducation;
  backgrounds: Record<string, number>;  // corporate, private_equity, consulting, etc.
  seniority: Record<string, number>;    // partner, director, associate, etc.
  hiring: {
    new_hires_last_1y: number;
    new_hires_last_2y: number;
    new_hires_last_3y: number;
    new_hires_last_4y: number;
    avg_tenure_years: number;
  };
  demographics: {
    gender_male_pct: number;
    gender_female_pct: number;
    gender_unknown_pct: number;
    avg_years_experience: number;
    avg_estimated_age: number;
  };
}
