/**
 * Fund Data Quality Scoring — Internal-only module
 *
 * Evaluates every data dimension for each fund (0-100 per section, 0-100 composite).
 * NOT displayed on the website. Used to generate a ranked report so we know
 * which funds need the most data improvement work.
 *
 * Sections scored: Profile (15%), AIFI (20%), Portfolio (40%), Signals (25%)
 * Team is excluded (dummy/placeholder data until real LinkedIn scraping is implemented).
 *
 * Cache: one module-level variable, same no-TTL pattern as data.ts.
 */

import {
  getFundBySlug,
  getAllFunds,
  getPortfolioForFund,
  getDealsForFund,
  getSignalsForFund,
  isMegaFund,
} from './data';
import type { PortfolioCompany } from './data';
import type { Fund, Signal, Deal } from '@fundradar/shared';

// ─── Types ──────────────────────────────────────────────────────────

export interface SectionScore {
  score: number;         // 0-100
  maxPoints: number;
  earnedPoints: number;
  details: string[];     // human-readable: what scored/missed
}

export interface FundQualityResult {
  slug: string;
  name: string;
  compositeScore: number;   // 0-100 weighted
  grade: 'A' | 'B' | 'C' | 'D' | 'F';
  profileScore: SectionScore;
  aifiScore: SectionScore;
  portfolioScore: SectionScore;
  signalScore: SectionScore;
  redFlags: string[];
}

// ─── Cache ──────────────────────────────────────────────────────────

let cachedQualities: Record<string, FundQualityResult> | null = null;

// ─── Composite Weights ──────────────────────────────────────────────

const WEIGHTS = {
  portfolio: 0.40,
  signals: 0.25,
  aifi: 0.20,
  profile: 0.15,
} as const;

// ─── Grade Mapping ──────────────────────────────────────────────────

function computeGrade(score: number): 'A' | 'B' | 'C' | 'D' | 'F' {
  if (score >= 80) return 'A';
  if (score >= 60) return 'B';
  if (score >= 40) return 'C';
  if (score >= 20) return 'D';
  return 'F';
}

// ─── Helpers ────────────────────────────────────────────────────────

function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

function pct(count: number, total: number): number {
  if (total === 0) return 0;
  return count / total;
}

// ─── Section A: Profile Score (max 100) ─────────────────────────────

function scoreProfile(fund: Fund): SectionScore {
  let earned = 0;
  const max = 100;
  const details: string[] = [];

  // Name + slug baseline (10 pts — always true)
  earned += 10;
  details.push('+10 name/slug baseline');

  // Category not 'unknown' (15 pts)
  if (fund.category !== 'unknown') {
    earned += 15;
    details.push(`+15 category: ${fund.category}`);
  } else {
    details.push('  0 category unknown');
  }

  // Has website (15 pts)
  if (fund.website) {
    earned += 15;
    details.push('+15 has website');
  } else {
    details.push('  0 no website');
  }

  // Has description >= 20 chars (15 pts)
  const descLen = fund.description?.length ?? 0;
  if (descLen >= 20) {
    earned += 15;
    details.push(`+15 description (${descLen} chars)`);
  } else {
    details.push(`  0 description too short (${descLen} chars)`);
  }

  // Description quality > 100 chars (5 pts)
  if (descLen > 100) {
    earned += 5;
    details.push('+5  description quality >100 chars');
  }

  // Has hq_city (10 pts)
  if (fund.hq_city) {
    earned += 10;
    details.push('+10 has hq_city');
  } else {
    details.push('  0 no hq_city');
  }

  // Has hq_region (5 pts)
  if (fund.hq_region) {
    earned += 5;
    details.push('+5  has hq_region');
  } else {
    details.push('  0 no hq_region');
  }

  // Has >= 1 sector_tag (10 pts)
  if (fund.sector_tags.length > 0) {
    earned += 10;
    details.push(`+10 has sector_tags (${fund.sector_tags.length})`);
  } else {
    details.push('  0 no sector_tags');
  }

  // Has >= 3 sector_tags (5 pts)
  if (fund.sector_tags.length >= 3) {
    earned += 5;
    details.push('+5  3+ sector_tags');
  }

  // Has >= 1 strategy_tag (10 pts)
  if (fund.strategy_tags.length > 0) {
    earned += 10;
    details.push(`+10 has strategy_tags (${fund.strategy_tags.length})`);
  } else {
    details.push('  0 no strategy_tags');
  }

  return { score: Math.round((earned / max) * 100), maxPoints: max, earnedPoints: earned, details };
}

// ─── Section B: AIFI Score (max 100) ────────────────────────────────

function scoreAifi(fund: Fund): SectionScore {
  let earned = 0;
  const max = 100;
  const details: string[] = [];

  // Has AUM (20 pts)
  if (fund.aum_eur != null && fund.aum_eur > 0) {
    earned += 20;
    details.push(`+20 has AUM (€${(fund.aum_eur / 1e6).toFixed(0)}M)`);
  } else {
    details.push('  0 no AUM');
  }

  // Has num_portfolio_companies (15 pts)
  if (fund.num_portfolio_companies != null && fund.num_portfolio_companies > 0) {
    earned += 15;
    details.push(`+15 has num_portfolio_companies (${fund.num_portfolio_companies})`);
  } else {
    details.push('  0 no num_portfolio_companies');
  }

  // Has num_funds (10 pts)
  if (fund.num_funds != null && fund.num_funds > 0) {
    earned += 10;
    details.push(`+10 has num_funds (${fund.num_funds})`);
  } else {
    details.push('  0 no num_funds');
  }

  // Has num_executives (10 pts)
  if (fund.num_executives != null && fund.num_executives > 0) {
    earned += 10;
    details.push(`+10 has num_executives (${fund.num_executives})`);
  } else {
    details.push('  0 no num_executives');
  }

  // Has investment range — min or max (10 pts)
  const hasMin = fund.investment_min_eur != null && fund.investment_min_eur > 0;
  const hasMax = fund.investment_max_eur != null && fund.investment_max_eur > 0;
  if (hasMin || hasMax) {
    earned += 10;
    details.push('+10 has investment range (partial)');
  } else {
    details.push('  0 no investment range');
  }

  // Has complete range — both (5 pts)
  if (hasMin && hasMax) {
    earned += 5;
    details.push('+5  complete investment range');
  }

  // Has geographies (5 pts)
  if (fund.geographies && fund.geographies.length > 0) {
    earned += 5;
    details.push(`+5  has geographies (${fund.geographies.length})`);
  } else {
    details.push('  0 no geographies');
  }

  // Has average_investment (5 pts)
  if (fund.average_investment && fund.average_investment.length > 0) {
    earned += 5;
    details.push(`+5  has average_investment (${fund.average_investment.length})`);
  } else {
    details.push('  0 no average_investment');
  }

  // Has asset_class (5 pts)
  if (fund.asset_class && fund.asset_class.length > 0) {
    earned += 5;
    details.push(`+5  has asset_class (${fund.asset_class.length})`);
  } else {
    details.push('  0 no asset_class');
  }

  // Has any contact info (5 pts)
  const hasContactName = fund.contact_name != null && fund.contact_name.length > 0;
  const hasContactEmail = fund.contact_email != null && fund.contact_email.length > 0;
  const hasContactPhone = fund.contact_phone != null && fund.contact_phone.length > 0;
  if (hasContactName || hasContactEmail || hasContactPhone) {
    earned += 5;
    details.push('+5  has contact info');
  } else {
    details.push('  0 no contact info');
  }

  // Has full contact — all 3 (5 pts)
  if (hasContactName && hasContactEmail && hasContactPhone) {
    earned += 5;
    details.push('+5  full contact (name+email+phone)');
  }

  // Has SFDR data (5 pts) — even 0 counts as having data
  if (typeof fund.num_sfdr_article_8 === 'number') {
    earned += 5;
    details.push(`+5  has SFDR data (${fund.num_sfdr_article_8})`);
  } else {
    details.push('  0 no SFDR data');
  }

  return { score: Math.round((earned / max) * 100), maxPoints: max, earnedPoints: earned, details };
}

// ─── Section C: Portfolio Score (max 100) — HIGHEST WEIGHTED ────────

function scorePortfolio(fund: Fund): SectionScore {
  let earned = 0;
  const max = 100;
  const details: string[] = [];
  const redFlags: string[] = [];

  const portfolio = getPortfolioForFund(fund.slug);
  const deals = getDealsForFund(fund.slug);

  // Has any companies (10 pts)
  if (portfolio.length > 0) {
    earned += 10;
    details.push(`+10 has portfolio (${portfolio.length} companies)`);
  } else {
    details.push('  0 no portfolio data');
    redFlags.push('No portfolio data at all');
  }

  // Has current companies (20 pts)
  const currentCount = portfolio.filter(c => c.status === 'current').length;
  if (currentCount > 0) {
    earned += 20;
    details.push(`+20 has current companies (${currentCount})`);
  } else {
    details.push('  0 no current companies');
    if (portfolio.length > 0) {
      redFlags.push('No current assets');
    }
  }

  // Current count graduated (15 pts)
  if (currentCount >= 10) {
    earned += 15;
    details.push('+15 10+ current companies');
  } else if (currentCount >= 5) {
    earned += 10;
    details.push('+10 5-9 current companies');
  } else if (currentCount >= 1) {
    earned += 5;
    details.push('+5  1-4 current companies');
  }

  // Has website-sourced data (10 pts)
  const websiteSourced = portfolio.filter(c => c.data_source === 'fund_website').length;
  if (websiteSourced > 0) {
    earned += 10;
    details.push(`+10 has website-sourced data (${websiteSourced})`);
  } else {
    details.push('  0 no website-sourced data');
    if (portfolio.length > 0 && portfolio.every(c => c.data_source === 'pem')) {
      redFlags.push('Portfolio only from PEM (no website data)');
    }
  }

  // Source diversity >= 2 (5 pts)
  const dataSources = new Set(portfolio.map(c => c.data_source).filter(Boolean));
  if (dataSources.size >= 2) {
    earned += 5;
    details.push(`+5  source diversity (${dataSources.size} sources)`);
  } else {
    details.push(`  0 single source (${dataSources.size})`);
  }

  // Sector coverage (10 pts)
  const withSector = portfolio.filter(c => c.sector != null && c.sector.length > 0).length;
  const sectorPct = pct(withSector, portfolio.length);
  if (sectorPct >= 0.75) {
    earned += 10;
    details.push(`+10 sector coverage ${(sectorPct * 100).toFixed(0)}%`);
  } else if (sectorPct >= 0.50) {
    earned += 6;
    details.push(`+6  sector coverage ${(sectorPct * 100).toFixed(0)}%`);
  } else if (sectorPct >= 0.25) {
    earned += 3;
    details.push(`+3  sector coverage ${(sectorPct * 100).toFixed(0)}%`);
  } else {
    details.push(`  0 sector coverage ${(sectorPct * 100).toFixed(0)}%`);
  }

  // Companies have websites (5 pts)
  const withWebsite = portfolio.filter(c => c.website != null && c.website.length > 0).length;
  const websitePct = pct(withWebsite, portfolio.length);
  if (websitePct >= 0.50) {
    earned += 5;
    details.push(`+5  company websites ${(websitePct * 100).toFixed(0)}%`);
  } else if (websitePct >= 0.25) {
    earned += 2;
    details.push(`+2  company websites ${(websitePct * 100).toFixed(0)}%`);
  } else {
    details.push(`  0 company websites ${(websitePct * 100).toFixed(0)}%`);
  }

  // Entry dates present (5 pts)
  const withDate = portfolio.filter(c => c.entry_date || c.investment_date).length;
  const datePct = pct(withDate, portfolio.length);
  if (datePct >= 0.50) {
    earned += 5;
    details.push(`+5  entry dates ${(datePct * 100).toFixed(0)}%`);
  } else if (datePct >= 0.25) {
    earned += 2;
    details.push(`+2  entry dates ${(datePct * 100).toFixed(0)}%`);
  } else {
    details.push(`  0 entry dates ${(datePct * 100).toFixed(0)}%`);
  }

  // Has PEM deal history (5 pts)
  if (deals.length > 0) {
    earned += 5;
    details.push(`+5  has PEM deals (${deals.length})`);
  } else {
    details.push('  0 no PEM deals');
  }

  // PEM count graduated (5 pts)
  if (deals.length >= 10) {
    earned += 5;
    details.push('+5  10+ PEM deals');
  } else if (deals.length >= 5) {
    earned += 3;
    details.push('+3  5-9 PEM deals');
  } else if (deals.length >= 1) {
    earned += 2;
    details.push('+2  1-4 PEM deals');
  }

  // Avg confidence >= 0.7 (5 pts)
  if (portfolio.length > 0) {
    const avgConf = mean(portfolio.map(c => c.confidence));
    if (avgConf >= 0.7) {
      earned += 5;
      details.push(`+5  avg confidence ${avgConf.toFixed(2)}`);
    } else {
      details.push(`  0 avg confidence ${avgConf.toFixed(2)}`);
    }
  }

  // Additional red flags
  if (deals.length >= 5 && currentCount === 0) {
    redFlags.push(`${deals.length} PEM deals but 0 current portfolio`);
  }
  if (portfolio.length > 0 && portfolio.every(c => c.status === 'exited')) {
    redFlags.push('All assets marked as exited');
  }

  return {
    score: Math.round((earned / max) * 100),
    maxPoints: max,
    earnedPoints: earned,
    details,
    // Red flags stored temporarily — merged into FundQualityResult.redFlags by caller
    ...(redFlags.length > 0 ? { _redFlags: redFlags } : {}),
  } as SectionScore & { _redFlags?: string[] };
}

// ─── Section D: Signal Score (max 100) ──────────────────────────────

function scoreSignals(fund: Fund): SectionScore {
  let earned = 0;
  const max = 100;
  const details: string[] = [];
  const redFlags: string[] = [];

  const signals = getSignalsForFund(fund.slug);

  // ── Quantity & diversity (40 pts) ──

  // Has any signals (10 pts)
  if (signals.length > 0) {
    earned += 10;
    details.push(`+10 has signals (${signals.length})`);
  } else {
    details.push('  0 no signals');
    redFlags.push('No signals');
  }

  // Signal count graduated (10 pts)
  if (signals.length >= 10) {
    earned += 10;
    details.push('+10 10+ signals');
  } else if (signals.length >= 5) {
    earned += 6;
    details.push('+6  5-9 signals');
  } else if (signals.length >= 1) {
    earned += 3;
    details.push('+3  1-4 signals');
  }

  // Type diversity (10 pts)
  const signalTypes = new Set(signals.map(s => s.signal_type));
  const typeCount = signalTypes.size;
  if (typeCount >= 4) {
    earned += 10;
    details.push(`+10 type diversity (${typeCount} types)`);
  } else if (typeCount >= 3) {
    earned += 8;
    details.push(`+8  type diversity (${typeCount} types)`);
  } else if (typeCount >= 2) {
    earned += 5;
    details.push(`+5  type diversity (${typeCount} types)`);
  } else if (typeCount >= 1) {
    earned += 2;
    details.push(`+2  type diversity (${typeCount} type)`);
  }

  // Has deal/exit signals (10 pts)
  if (signalTypes.has('deal_announced') || signalTypes.has('exit_announced')) {
    earned += 10;
    details.push('+10 has deal/exit signals');
  } else {
    details.push('  0 no deal/exit signals');
  }

  // Only website_change signals
  if (signals.length > 0 && signals.every(s => s.signal_type === 'website_change')) {
    redFlags.push('Only website_change signals');
  }

  // ── Individual signal quality (35 pts) ──
  // These fields are written by Python but not declared in the TS Signal type
  // Read via (signal as any) — see CLAUDE.md notes on undeclared fields

  if (signals.length > 0) {
    // Avg quality_score >= 70 (10 pts)
    const qualityScores = signals
      .map(s => (s as any).quality_score as number | undefined)
      .filter((v): v is number => typeof v === 'number');
    if (qualityScores.length > 0) {
      const avgQuality = mean(qualityScores);
      if (avgQuality >= 70) {
        earned += 10;
        details.push(`+10 avg quality_score ${avgQuality.toFixed(1)}`);
      } else {
        details.push(`  0 avg quality_score ${avgQuality.toFixed(1)}`);
      }

      // Avg quality_score >= 85 bonus (5 pts)
      if (avgQuality >= 85) {
        earned += 5;
        details.push('+5  high quality bonus (>=85)');
      }

      // Low quality red flag
      if (avgQuality < 60) {
        redFlags.push(`Low signal quality — avg quality_score ${avgQuality.toFixed(0)}`);
      }
    } else {
      details.push('  0 no quality_score data');
    }

    // Italy-relevant ratio >= 50% (10 pts)
    const italyRelevant = signals.filter(s => (s as any).italy_relevant === true).length;
    const italyRatio = pct(italyRelevant, signals.length);
    if (italyRatio >= 0.50) {
      earned += 10;
      details.push(`+10 Italy-relevant ratio ${(italyRatio * 100).toFixed(0)}%`);
    } else {
      details.push(`  0 Italy-relevant ratio ${(italyRatio * 100).toFixed(0)}%`);
    }
    if (italyRatio < 0.20) {
      redFlags.push(`Low Italy relevance — ${(italyRatio * 100).toFixed(0)}% signals Italy-relevant`);
    }

    // Avg relevance_score >= 0.2 (5 pts)
    const relevanceScores = signals
      .map(s => (s as any).relevance_score as number | undefined)
      .filter((v): v is number => typeof v === 'number');
    if (relevanceScores.length > 0) {
      const avgRelevance = mean(relevanceScores);
      if (avgRelevance >= 0.2) {
        earned += 5;
        details.push(`+5  avg relevance_score ${avgRelevance.toFixed(3)}`);
      } else {
        details.push(`  0 avg relevance_score ${avgRelevance.toFixed(3)}`);
      }
    } else {
      details.push('  0 no relevance_score data');
    }

    // what_changed quality — >=50% over 30 chars (5 pts)
    const meaningfulWc = signals.filter(s => (s.what_changed || '').length > 30).length;
    if (pct(meaningfulWc, signals.length) >= 0.50) {
      earned += 5;
      details.push(`+5  what_changed quality (${meaningfulWc}/${signals.length} >30 chars)`);
    } else {
      details.push(`  0 what_changed quality (${meaningfulWc}/${signals.length} >30 chars)`);
    }
  }

  // ── Signal availability and sourcing (25 pts) ──

  if (signals.length > 0) {
    // Award based on signal availability, not recency:
    // high-value historical signals should still count for completeness.
    if (signals.length >= 2) {
      earned += 15;
      details.push(`+15 signal availability (${signals.length} signals)`);
    } else if (signals.length === 1) {
      earned += 5;
      details.push('+5  signal availability (1 signal)');
    } else {
      details.push('  0 no signals');
      redFlags.push('No signals');
    }

    // All have source_url (5 pts)
    const withSourceUrl = signals.filter(s => s.source_url && s.source_url.length > 0).length;
    if (withSourceUrl === signals.length) {
      earned += 5;
      details.push('+5  all signals have source_url');
    } else {
      details.push(`  0 ${signals.length - withSourceUrl}/${signals.length} missing source_url`);
    }
  }

  return {
    score: Math.round((earned / max) * 100),
    maxPoints: max,
    earnedPoints: earned,
    details,
    ...(redFlags.length > 0 ? { _redFlags: redFlags } : {}),
  } as SectionScore & { _redFlags?: string[] };
}

// ─── Public API ─────────────────────────────────────────────────────

export function computeFundQuality(fundSlug: string): FundQualityResult | null {
  const fund = getFundBySlug(fundSlug);
  if (!fund) return null;

  const profileScore = scoreProfile(fund);
  const aifiScore = scoreAifi(fund);
  const portfolioResult = scorePortfolio(fund) as SectionScore & { _redFlags?: string[] };
  const signalResult = scoreSignals(fund) as SectionScore & { _redFlags?: string[] };

  // Extract red flags from section scores
  const redFlags: string[] = [];

  // Profile red flags
  if (!fund.website) redFlags.push('No website URL');
  if (fund.category === 'unknown') redFlags.push('Category unknown');

  // AIFI red flag
  const hasAnyAifi = (fund.aum_eur != null) ||
    (fund.num_funds != null) ||
    (fund.num_portfolio_companies != null) ||
    (fund.num_executives != null);
  if (!hasAnyAifi) redFlags.push('No AIFI data');

  // Portfolio red flags
  if (portfolioResult._redFlags) redFlags.push(...portfolioResult._redFlags);

  // Signal red flags
  if (signalResult._redFlags) redFlags.push(...signalResult._redFlags);

  // Clean section scores (remove internal _redFlags)
  const portfolioScore: SectionScore = {
    score: portfolioResult.score,
    maxPoints: portfolioResult.maxPoints,
    earnedPoints: portfolioResult.earnedPoints,
    details: portfolioResult.details,
  };
  const signalScore: SectionScore = {
    score: signalResult.score,
    maxPoints: signalResult.maxPoints,
    earnedPoints: signalResult.earnedPoints,
    details: signalResult.details,
  };

  // Composite score
  const compositeScore = Math.round(
    portfolioScore.score * WEIGHTS.portfolio +
    signalScore.score * WEIGHTS.signals +
    aifiScore.score * WEIGHTS.aifi +
    profileScore.score * WEIGHTS.profile
  );

  return {
    slug: fund.slug,
    name: fund.name,
    compositeScore,
    grade: computeGrade(compositeScore),
    profileScore,
    aifiScore,
    portfolioScore,
    signalScore,
    redFlags,
  };
}

export function computeAllFundQualities(): Record<string, FundQualityResult> {
  if (cachedQualities) return cachedQualities;

  const funds = getAllFunds();
  const results: Record<string, FundQualityResult> = {};

  for (const fund of funds) {
    const result = computeFundQuality(fund.slug);
    if (result) {
      results[fund.slug] = result;
    }
  }

  cachedQualities = results;
  return cachedQualities;
}
