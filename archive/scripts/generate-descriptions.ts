/**
 * Generate descriptions for funds that are missing them.
 *
 * Reads db.json, generates template-based descriptions
 * from existing metadata (category, city, strategies, sectors, AUM), and
 * writes updated files back.
 *
 * One-time script. Safe to re-run — only overwrites null descriptions.
 *
 * Usage: cd scripts && npx tsx generate-descriptions.ts
 */

import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import type { Fund } from '@fundradar/shared';

const PROJECT_ROOT = join(process.cwd(), '..');
const DB_PATH = join(PROJECT_ROOT, 'data', 'db.json');

// ─── Category labels ────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  pe: 'private equity',
  vc: 'venture capital',
  infra: 'infrastructure investment',
  sovereign: 'sovereign investment',
  asset_manager: 'asset management',
  multi_strategy: 'multi-strategy investment',
  unknown: 'investment',
};

// ─── Known international funds (not Italian-HQ) ─────────────────────

const INTERNATIONAL_FUNDS = new Set([
  'advent-international',
  'apax-partners',
  'apollo',
  'ardian',
  'ares-management',
  'astorg',
  'bain-capital',
  'bc-partners',
  'blackstone',
  'bluegem',
  'bridgepoint',
  'carlyle',
  'cinven',
  'cvc-capital-partners',
  'cvc-dif',
  'eiffel',
  'eos-im',
  'eqt',
  'equinox-aifm',
  'h-i-g-capital',
  'investindustrial',
  'kkr',
  'l-catterton',
  'macquarie',
  'oakley-capital',
  'pai-partners',
  'partners-group',
  'permira',
  'perwyn',
  'portobello-capital',
  'ring-capital',
  'sofinnova-partners',
  'tikehau-capital',
  'towerbrook',
  'triton',
]);

// Non-Italian cities — detect international funds by city
const NON_ITALIAN_CITIES = new Set([
  'london', 'paris', 'parigi', 'new york', 'madrid', 'luxembourg',
  'amsterdam', 'zurich', 'frankfurt', 'munich', 'berlin', 'dublin',
  'brussels', 'geneva', 'stockholm', 'oslo', 'copenhagen',
]);

// ─── Tag formatting ─────────────────────────────────────────────────

// Short strategy/sector tags that need full expansion
const TAG_EXPANSIONS: Record<string, string> = {
  'pe': 'private equity',
  'vc': 'venture capital',
  'multi-sector': 'multi-sector',
  'multi sector': 'multi-sector',
};

function formatTag(tag: string): string {
  const lower = tag.toLowerCase().trim();
  // Check for exact match expansions first
  if (TAG_EXPANSIONS[lower]) return TAG_EXPANSIONS[lower];

  return tag
    .replace(/-/g, ' ')
    .replace(/\bAnd\b/gi, '&')
    .replace(/\bOther\b/gi, '')
    .replace(/\bInformation\b/gi, 'information')
    .replace(/\bTelco\b/gi, 'telecom')
    .toLowerCase()
    .trim();
}

function formatTagList(tags: string[]): string {
  const formatted = tags.map(formatTag).filter(t => t.length > 0);
  if (formatted.length === 0) return '';
  if (formatted.length === 1) return formatted[0];
  if (formatted.length === 2) return `${formatted[0]} and ${formatted[1]}`;
  return formatted.slice(0, -1).join(', ') + ', and ' + formatted[formatted.length - 1];
}

function articleFor(word: string): string {
  return /^[aeiou]/i.test(word) ? 'an' : 'a';
}

function formatAum(aum: number): string {
  if (aum >= 1e12) return `€${(aum / 1e9).toFixed(0)}B`;
  if (aum >= 1e9) {
    const billions = aum / 1e9;
    return billions >= 10 ? `€${billions.toFixed(0)}B` : `€${billions.toFixed(1)}B`;
  }
  return `€${(aum / 1e6).toFixed(0)}M`;
}

// ─── Description generation ─────────────────────────────────────────

function generateDescription(fund: Fund): string | null {
  const catLabel = CATEGORY_LABELS[fund.category] || 'investment';
  const city = fund.hq_city && fund.hq_city !== '-' ? fund.hq_city : null;
  const isInternational = INTERNATIONAL_FUNDS.has(fund.slug) ||
    (city != null && NON_ITALIAN_CITIES.has(city.toLowerCase()));

  // Build strategies phrase
  const strategies = fund.strategy_tags.length > 0
    ? formatTagList(fund.strategy_tags)
    : null;

  // Build sectors phrase
  const sectors = fund.sector_tags.length > 0
    ? formatTagList(fund.sector_tags)
    : null;

  // AUM phrase
  const aumPhrase = fund.aum_eur != null && fund.aum_eur > 0
    ? ` with ${formatAum(fund.aum_eur)} in assets under management`
    : '';

  // Build the core description
  let desc: string;

  if (isInternational) {
    const locationPhrase = city ? ` with Italian operations based in ${city}` : ' with Italian operations';
    desc = `${fund.name} is ${articleFor(catLabel)} ${catLabel} firm${locationPhrase}${aumPhrase}`;
  } else if (city) {
    desc = `${fund.name} is an Italian ${catLabel} firm based in ${city}${aumPhrase}`;
  } else {
    desc = `${fund.name} is an Italian ${catLabel} firm${aumPhrase}`;
  }

  // Add strategy/sector info
  // Handle "multi-sector" specially — don't say "the multi-sector sectors"
  const isMultiSector = fund.sector_tags.length === 1 &&
    fund.sector_tags[0].toLowerCase().replace(/-/g, ' ').includes('multi');
  const sectorPhrase = isMultiSector ? 'across multiple sectors' : (sectors ? `across the ${sectors} sectors` : null);

  if (strategies && sectorPhrase) {
    desc += `, focused on ${strategies} investments ${sectorPhrase}.`;
  } else if (strategies) {
    desc += `, focused on ${strategies} investments.`;
  } else if (sectorPhrase) {
    desc += `, investing ${sectorPhrase}.`;
  } else {
    desc += '.';
  }

  // Verify length — must be >= 20 chars for scoring, target >100 for bonus
  if (desc.length < 20) return null;

  return desc;
}

// ─── Main ───────────────────────────────────────────────────────────

interface Database {
  generated_at: string;
  source: string;
  pem_manifest: unknown;
  funds: Fund[];
  deals: unknown[];
  signals: unknown[];
  [key: string]: unknown;
}

// Descriptions that were manually written — never overwrite these
const HAND_WRITTEN_SLUGS = new Set([
  'sosteneo',  // manually crafted
  'perwyn',                            // manually crafted
  'cvc-dif',                           // manually crafted
]);

function main() {
  const forceAll = process.argv.includes('--force');
  console.log(`Generating descriptions (mode: ${forceAll ? 'FORCE regenerate all' : 'null-only'})...\n`);

  // ── db.json ──
  const db: Database = JSON.parse(readFileSync(DB_PATH, 'utf-8'));
  let dbUpdated = 0;

  for (const fund of db.funds) {
    if (HAND_WRITTEN_SLUGS.has(fund.slug)) continue;
    if (!forceAll && fund.description != null) continue;

    const desc = generateDescription(fund);
    if (desc) {
      fund.description = desc;
      dbUpdated++;
      console.log(`  [db] ${fund.slug}: ${desc.substring(0, 80)}...`);
    } else {
      console.log(`  [db] ${fund.slug}: SKIPPED (could not generate)`);
    }
  }

  writeFileSync(DB_PATH, JSON.stringify(db, null, 2) + '\n');
  console.log(`\nUpdated ${dbUpdated} fund descriptions in db.json`);

  console.log(`\nTotal: ${dbUpdated} descriptions generated`);
}

main();
