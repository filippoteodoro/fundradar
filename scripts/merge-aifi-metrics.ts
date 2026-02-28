/**
 * Merge AIFI scraper metrics into db.json
 *
 * This script reads the rich data from aifi_members.json (Python scraper output)
 * and merges AUM, fund count, portfolio companies, executives, etc. into db.json
 *
 * Run after: pnpm worker:aifi
 * Usage: pnpm merge-aifi
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';
import type { Fund } from '@fundradar/shared';

const PROJECT_ROOT = join(process.cwd(), '..');
const AIFI_MEMBERS_PATH = join(PROJECT_ROOT, 'data', 'derived', 'aifi_members.json');
const COORDINATES_PATH = join(PROJECT_ROOT, 'data', 'derived', 'fund_coordinates.json');
const DB_PATH = join(PROJECT_ROOT, 'data', 'db.json');

// AIFI members excluded from Fundradar — not relevant PE/VC funds.
// Global asset managers, banks, regional development entities, niche/micro platforms.
const EXCLUDED_SLUGS = new Set([
  // Banks & banking subsidiaries
  'intesa-sanpaolo-direzione-group-shareholdings',
  'bnp-paribas-bnl-equity-investments',
  'banca-generali',
  'banco-bpm-invest-sgr',
  'mediocredito-centrale',
  'lion-river-i-nv',
  // Global asset managers (AIFI membership ≠ Italian PE/VC focus)
  'amundi',
  'blackrock',
  'bnp-paribas-asset-management-europe',
  'swiss-life-asset-managers-luxembourg-succursale-italia',
  // Regional/public development entities
  'fvg-plus',
  'trentino-sviluppo',
  'finlombarda-s-p-a',
  'lazio-innova',
  'ligurcapital',
  'gepafin',
  // Asset managers / niche
  'avm-sgr-spa-gestore-euveca-societ-benefit',
  'f-rstenberg-sgr',
  'ersel',
  'ersel-asset-management-sgr',
  'zenit-sgr',
  // Not PE/VC funds (asset managers, holding companies, export credit).
  // Retained as explicit exclusions for compatibility with AIFI scrape naming.
  'generali-investments',
  'simest',
  'sienna-investment-managers-italia-sgr',
  // Public promotional institutions (not PE/VC funds)
  'invitalia',
  // Insufficient data or out of scope
  'aks-a-sgr',
  'arm-nia-sgr',
  'antares-advisory-srl',
  'doorway',
  'l-catterton-italy-advisors',
  'overseas-industries',
  'quant-ico-investment-club-opportunities',
]);

interface AifiMember {
  name: string;
  slug: string;
  aifi_url: string;
  city: string | null;
  address: string | null;
  country: string | null;
  phone: string | null;
  email: string | null;
  website: string | null;
  contact_name: string | null;
  aum_eur: number | null;
  num_funds: number | null;
  num_portfolio_companies: number | null;
  num_executives: number | null;
  num_sfdr_article_8: number | null;
  investment_min_eur: number | null;
  investment_max_eur: number | null;
  strategies: string[];
  sectors: string[];
  geographies: string[];
  asset_classes: string[];
  description: string | null;
  scraped_at: string;
}

interface AifiMembersFile {
  scraped_at: string;
  source_url: string;
  member_count: number;
  members: AifiMember[];
}

interface Database {
  generated_at: string;
  source: string;
  pem_manifest: unknown;
  funds: Fund[];
  deals: unknown[];
  signals: unknown[];
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[àáâãäå]/g, 'a')
    .replace(/[èéêë]/g, 'e')
    .replace(/[ìíîï]/g, 'i')
    .replace(/[òóôõö]/g, 'o')
    .replace(/[ùúûü]/g, 'u')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

function normalizeForMatching(name: string): string {
  return name
    .toLowerCase()
    .replace(/[àáâãäå]/g, 'a')
    .replace(/[èéêë]/g, 'e')
    .replace(/[ìíîï]/g, 'i')
    .replace(/[òóôõö]/g, 'o')
    .replace(/[ùúûü]/g, 'u')
    .replace(/\s+/g, ' ')
    .trim();
}

async function main() {
  console.log('Merging AIFI metrics into database...\n');

  // Check if files exist
  if (!existsSync(AIFI_MEMBERS_PATH)) {
    console.error(`Error: ${AIFI_MEMBERS_PATH} not found.`);
    console.error('Run "pnpm worker:aifi" first to scrape AIFI member data.');
    process.exit(1);
  }

  if (!existsSync(DB_PATH)) {
    console.error(`Error: ${DB_PATH} not found.`);
    console.error('Run "pnpm seed" first to create the database.');
    process.exit(1);
  }

  // Load files
  const aifiData: AifiMembersFile = JSON.parse(readFileSync(AIFI_MEMBERS_PATH, 'utf-8'));
  const db: Database = JSON.parse(readFileSync(DB_PATH, 'utf-8'));

  console.log(`AIFI members file: ${aifiData.member_count} members (scraped ${aifiData.scraped_at})`);
  console.log(`Database: ${db.funds.length} funds\n`);

  // Create lookup maps for matching
  const aifiBySlug = new Map<string, AifiMember>();
  const aifiByNormalizedName = new Map<string, AifiMember>();

  for (const member of aifiData.members) {
    aifiBySlug.set(member.slug, member);
    aifiByNormalizedName.set(normalizeForMatching(member.name), member);
  }

  // Load coordinates file (optional)
  let coordinates: Record<string, { lat: number | null; lng: number | null; source: string }> = {};
  if (existsSync(COORDINATES_PATH)) {
    coordinates = JSON.parse(readFileSync(COORDINATES_PATH, 'utf-8'));
    console.log(`Coordinates file: ${Object.keys(coordinates).length} entries\n`);
  } else {
    console.log('No coordinates file found (run geocode_funds.py to generate)\n');
  }

  // Track stats
  let matched = 0;
  let unmatched = 0;
  let metricsAdded = 0;
  let coordsMerged = 0;

  // Merge metrics into each fund
  for (const fund of db.funds) {
    // Skip excluded entities
    if (EXCLUDED_SLUGS.has(fund.slug)) continue;

    // Try to match by slug first, then by normalized name
    let aifiMember = aifiBySlug.get(fund.slug);

    if (!aifiMember) {
      aifiMember = aifiByNormalizedName.get(normalizeForMatching(fund.name));
    }

    if (!aifiMember) {
      // Try partial matching for edge cases
      const fundNameNorm = normalizeForMatching(fund.name);
      for (const [name, member] of aifiByNormalizedName) {
        if (name.includes(fundNameNorm) || fundNameNorm.includes(name)) {
          aifiMember = member;
          break;
        }
      }
    }

    if (aifiMember) {
      matched++;

      // Merge metrics (only if AIFI has data)
      // Skip AUM overwrite for funds with manually verified AUM (USD→EUR corrections)
      if (aifiMember.aum_eur !== null && !(fund as any).aum_eur_manual) {
        (fund as any).aum_eur = aifiMember.aum_eur;
        metricsAdded++;
      }
      if (aifiMember.num_funds !== null) {
        (fund as any).num_funds = aifiMember.num_funds;
        metricsAdded++;
      }
      if (aifiMember.num_portfolio_companies !== null) {
        (fund as any).num_portfolio_companies = aifiMember.num_portfolio_companies;
        metricsAdded++;
      }
      if (aifiMember.num_executives !== null) {
        (fund as any).num_executives = aifiMember.num_executives;
        metricsAdded++;
      }
      if (aifiMember.num_sfdr_article_8 !== null) {
        (fund as any).num_sfdr_article_8 = aifiMember.num_sfdr_article_8;
        metricsAdded++;
      }
      if (aifiMember.investment_min_eur !== null) {
        (fund as any).investment_min_eur = aifiMember.investment_min_eur;
        metricsAdded++;
      }
      if (aifiMember.investment_max_eur !== null) {
        (fund as any).investment_max_eur = aifiMember.investment_max_eur;
        metricsAdded++;
      }

      // Merge address from AIFI
      if (aifiMember.address) {
        (fund as any).hq_address = aifiMember.address;
        metricsAdded++;
      }

      // Add AIFI URL and scrape timestamp
      (fund as any).aifi_url = aifiMember.aifi_url;
      (fund as any).aifi_scraped_at = aifiMember.scraped_at;

      // Update timestamp
      fund.updated_at = new Date().toISOString();
    } else {
      unmatched++;
    }

    // Merge coordinates (independent of AIFI match — coordinates file covers all funds)
    const coords = coordinates[fund.slug];
    if (coords && coords.lat !== null && coords.lng !== null) {
      (fund as any).hq_lat = coords.lat;
      (fund as any).hq_lng = coords.lng;
      coordsMerged++;
    }
  }

  // Update database metadata
  db.generated_at = new Date().toISOString();

  // Write updated database
  writeFileSync(DB_PATH, JSON.stringify(db, null, 2));

  console.log('Merge complete!');
  console.log(`  Matched: ${matched}/${db.funds.length} funds`);
  console.log(`  Unmatched: ${unmatched} funds`);
  console.log(`  Metrics added: ${metricsAdded}`);
  console.log(`  Coordinates merged: ${coordsMerged}`);
  console.log(`\nWritten to ${DB_PATH}`);

  // Show sample of merged data
  const sampleFund = db.funds.find(f => (f as any).aum_eur);
  if (sampleFund) {
    console.log('\nSample merged fund:');
    console.log(`  Name: ${sampleFund.name}`);
    console.log(`  AUM: €${((sampleFund as any).aum_eur / 1_000_000_000).toFixed(2)}B`);
    console.log(`  Funds: ${(sampleFund as any).num_funds}`);
    console.log(`  Portfolio Companies: ${(sampleFund as any).num_portfolio_companies}`);
  }
}

main().catch(console.error);
