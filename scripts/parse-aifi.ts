/**
 * Parse AIFI CSV files and consolidate into a unified fund list
 * AIFI is the source of truth - only funds from AIFI are included
 */

import { parse } from 'csv-parse/sync';
import { readFileSync, readdirSync, existsSync, writeFileSync } from 'fs';
import { join, basename } from 'path';
import type { Fund, FundCategory } from '@fundradar/shared';

const PROJECT_ROOT = join(process.cwd(), '..');
const AIFI_DIR = join(PROJECT_ROOT, 'data', 'AIFI');
const OUTPUT_PATH = join(PROJECT_ROOT, 'data', 'db.json');

// Italian → English city names for well-known cities
const ITALIAN_TO_ENGLISH_CITY: Record<string, string> = {
  'Milano': 'Milan',
  'Roma': 'Rome',
  'Torino': 'Turin',
  'Firenze': 'Florence',
  'Napoli': 'Naples',
  'Venezia': 'Venice',
  'Genova': 'Genoa',
  'Padova': 'Padua',
  'Parigi': 'Paris',
  'Lussemburgo': 'Luxembourg',
};

function normalizeCity(city: string | null): string | null {
  if (!city) return null;
  return ITALIAN_TO_ENGLISH_CITY[city] || city;
}

// Entities to exclude (banks, wealth managers, non-PE entities).
// Keep raw AIFI files unchanged; enforce exclusion at parse time.
const EXCLUDED_NAMES = [
  'intesa sanpaolo',
  'bnp paribas bnl equity investments',
  'fvg plus',
  'yarpa investimenti',
  'finsea',
  'gruppo finsea',
  'finsea srl',
  'finsea s r l',
  'archivee finsea',
  'generali investments',
  'sienna investment managers',
];

function normalizeEntityName(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function isExcludedEntity(name: string): boolean {
  const normalizedName = normalizeEntityName(name);
  return EXCLUDED_NAMES.some(excluded => normalizedName.includes(excluded));
}

interface AifiRow {
  name: string;
  city: string;
  phone: string;
  email: string;
  website: string;
  contact: string;
}

interface FundAccumulator {
  name: string;
  city: string;
  phone: string;
  email: string;
  website: string;
  contact: string;
  sectors: Set<string>;
  geographies: Set<string>;
  investmentFocus: Set<string>;
  averageInvestment: Set<string>;
  assetClass: Set<string>;
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

function parseAifiCsv(filePath: string): AifiRow[] {
  const content = readFileSync(filePath, 'utf-8');
  const records = parse(content, {
    columns: false,
    skip_empty_lines: true,
    relax_quotes: true,
  });

  // Skip header row
  const dataRows = records.slice(1);

  return dataRows.map((row: string[]) => ({
    name: row[0]?.trim() || '',
    city: row[1]?.trim() || '',
    phone: row[2]?.trim() || '',
    email: row[3]?.trim() || '',
    website: (row[5] || row[6] || '').trim().replace(/\/+$/, ''),
    contact: row[7]?.trim() || '',
  }));
}

function getCsvFilesFromDir(dirPath: string): string[] {
  if (!existsSync(dirPath)) return [];
  return readdirSync(dirPath)
    .filter(f => f.endsWith('.csv'))
    .map(f => join(dirPath, f));
}

interface ManualFundEntry {
  name: string;
  city: string;
  phone: string;
  email: string;
  website: string;
  contact: string;
  category: string;
  categoryValue: string;
}

function parseReadmeFiles(): ManualFundEntry[] {
  const entries: ManualFundEntry[] = [];

  // Helper to parse fund blocks from README content
  function parseFundBlocks(content: string, category: string, categoryValue: string) {
    const lines = content.split('\n').map(l => l.trim());
    let currentFund: Partial<ManualFundEntry> | null = null;

    for (const line of lines) {
      if (line.startsWith('City:')) {
        if (currentFund) currentFund.city = line.replace('City:', '').trim();
      } else if (line.startsWith('Telephone:')) {
        if (currentFund) currentFund.phone = line.replace('Telephone:', '').trim();
      } else if (line.startsWith('Email:')) {
        if (currentFund) currentFund.email = line.replace('Email:', '').trim();
      } else if (line.startsWith('Website:')) {
        if (currentFund) currentFund.website = line.replace('Website:', '').trim();
      } else if (line.startsWith('Contact:')) {
        if (currentFund) currentFund.contact = line.replace('Contact:', '').trim();
        // Contact is the last field - save the fund
        if (currentFund?.name) {
          entries.push({
            name: currentFund.name,
            city: currentFund.city || '',
            phone: currentFund.phone || '',
            email: currentFund.email || '',
            website: currentFund.website || '',
            contact: currentFund.contact || '',
            category,
            categoryValue,
          });
        }
        currentFund = null;
      } else if (line && !line.startsWith('#') && !line.startsWith('The ') && !line.startsWith('Italian ') && /^[A-Z]/.test(line)) {
        // New fund name (starts with capital letter, not a header or description)
        currentFund = { name: line };
      }
    }
  }

  // Parse Average investment README (€20-50m funds)
  const avgInvReadme = join(AIFI_DIR, 'Average investment', 'README.md');
  if (existsSync(avgInvReadme)) {
    const content = readFileSync(avgInvReadme, 'utf-8');
    parseFundBlocks(content, 'averageInvestment', '€20-50m');
  }

  // Parse Geography README (Italian regional funds)
  const geoReadme = join(AIFI_DIR, 'Geography', 'README.md');
  if (existsSync(geoReadme)) {
    const content = readFileSync(geoReadme, 'utf-8');
    // Split by region headers
    const sections = content.split(/\n#/);

    for (const section of sections) {
      if (!section.trim() || section.startsWith('Italian regions')) continue;

      const lines = section.trim().split('\n');
      const regionMatch = lines[0].match(/^([A-Za-z]+)/);
      const region = regionMatch ? regionMatch[1] : '';

      if (region) {
        parseFundBlocks(section, 'geographies', region);
      }
    }
  }

  return entries;
}

function formatCategoryName(filename: string): string {
  // Remove .csv extension and format the name
  const name = basename(filename, '.csv');
  return name
    .replace(/\./g, ' ')  // Replace dots with spaces (e.g., private.equity)
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join('-')  // Keep hyphens for ranges like €5-20m
    .replace(/€(\d+) (\d+)/g, '€$1-$2') // Fix euro ranges like €50 100m -> €50-100m
    .replace(/venutre/gi, 'Venture'); // Fix typo in AIFI data
}

function inferFundCategory(fund: FundAccumulator): FundCategory {
  const assetClasses = Array.from(fund.assetClass).map(a => a.toLowerCase().replace(/\./g, ' '));
  const focuses = Array.from(fund.investmentFocus).map(f => f.toLowerCase());

  if (assetClasses.some(a => a.includes('venture capital'))) {
    return 'vc';
  }
  if (assetClasses.includes('infrastructure') || focuses.includes('infrastructure')) {
    return 'infra';
  }
  if (assetClasses.some(a => a.includes('private debt')) || focuses.some(f => f.includes('private debt') || f.includes('private-debt'))) {
    return 'debt';
  }
  if (focuses.some(f => f.includes('real estate') || f.includes('real-estate'))) {
    return 'real_estate';
  }
  if (focuses.some(f => f.includes('early stage') || f.includes('early-stage'))) {
    return 'vc';
  }
  if (focuses.some(f => f.includes('buy out') || f.includes('buyout') || f.includes('buy-out'))) {
    return 'pe';
  }
  if (focuses.some(f => f.includes('expansion'))) {
    return 'growth';
  }
  if (assetClasses.some(a => a.includes('private equity'))) {
    return 'pe';
  }
  return 'unknown';
}

async function main() {
  console.log('Parsing AIFI data...\n');

  const fundMap = new Map<string, FundAccumulator>();

  // Process each category
  const categories = [
    { dir: 'Sector', field: 'sectors' as const },
    { dir: 'Geography', field: 'geographies' as const },
    { dir: 'Investment focus', field: 'investmentFocus' as const },
    { dir: 'Average investment', field: 'averageInvestment' as const },
    { dir: 'Asset class', field: 'assetClass' as const },
  ];

  for (const { dir, field } of categories) {
    const dirPath = join(AIFI_DIR, dir);
    const csvFiles = getCsvFilesFromDir(dirPath);

    console.log(`Processing ${dir}: ${csvFiles.length} files`);

    for (const csvFile of csvFiles) {
      const categoryName = formatCategoryName(basename(csvFile));
      const rows = parseAifiCsv(csvFile);

      for (const row of rows) {
        if (!row.name) continue;

        // Skip excluded entities (banks, etc.)
        if (isExcludedEntity(row.name)) continue;

        const normalizedName = row.name.toLowerCase().trim();

        let fund = fundMap.get(normalizedName);

        if (!fund) {
          fund = {
            name: row.name,
            city: row.city,
            phone: row.phone,
            email: row.email,
            website: row.website,
            contact: row.contact,
            sectors: new Set(),
            geographies: new Set(),
            investmentFocus: new Set(),
            averageInvestment: new Set(),
            assetClass: new Set(),
          };
          fundMap.set(normalizedName, fund);
        }

        // Update fields if better data available
        if (!fund.city && row.city) fund.city = row.city;
        if (!fund.website && row.website) fund.website = row.website;
        if (!fund.email && row.email) fund.email = row.email;

        // Add category to appropriate set
        if (categoryName.toLowerCase() !== 'none' && categoryName.toLowerCase() !== 'aliante') {
          fund[field].add(categoryName);
        }
      }
    }
  }

  // Process README files for funds that couldn't be scraped
  console.log('\nProcessing README files for additional funds...');
  const manualEntries = parseReadmeFiles();
  console.log(`Found ${manualEntries.length} additional fund entries in README files`);

  for (const entry of manualEntries) {
    if (!entry.name) continue;

    // Apply the same exclusion rules used for CSV rows.
    if (isExcludedEntity(entry.name)) continue;

    const normalizedName = entry.name.toLowerCase().trim();
    let fund = fundMap.get(normalizedName);

    if (!fund) {
      fund = {
        name: entry.name,
        city: entry.city,
        phone: entry.phone,
        email: entry.email,
        website: entry.website,
        contact: entry.contact,
        sectors: new Set(),
        geographies: new Set(),
        investmentFocus: new Set(),
        averageInvestment: new Set(),
        assetClass: new Set(),
      };
      fundMap.set(normalizedName, fund);
    }

    // Update fields if better data available
    if (!fund.city && entry.city) fund.city = entry.city;
    if (!fund.website && entry.website) fund.website = entry.website;
    if (!fund.email && entry.email) fund.email = entry.email;
    if (!fund.contact && entry.contact) fund.contact = entry.contact;

    // Add category value
    if (entry.category === 'averageInvestment') {
      fund.averageInvestment.add(entry.categoryValue);
    } else if (entry.category === 'geographies') {
      fund.geographies.add(entry.categoryValue);
    }
  }

  console.log(`\nTotal unique funds from AIFI: ${fundMap.size}`);

  // Convert to Fund objects
  const now = new Date().toISOString();
  const funds: Fund[] = Array.from(fundMap.values()).map((f) => {
    const slug = slugify(f.name);
    const category = inferFundCategory(f);

    // Combine sectors from AIFI into sector_tags
    const sectorTags = Array.from(f.sectors).filter(s => s.toLowerCase() !== 'none');

    // Combine investment focus into strategy_tags
    const strategyTags = Array.from(f.investmentFocus);

    return {
      id: slug,
      slug,
      name: f.name,
      category,
      hq_city: normalizeCity(f.city || null),
      hq_region: 'Italy', // AIFI is Italian PE association
      website: f.website || null,
      strategy_tags: strategyTags,
      sector_tags: sectorTags,
      description: null,
      // Extended AIFI fields (stored in fund object for filtering)
      geographies: Array.from(f.geographies),
      average_investment: Array.from(f.averageInvestment),
      asset_class: Array.from(f.assetClass),
      contact_name: f.contact || null,
      contact_email: f.email || null,
      contact_phone: f.phone || null,
      created_at: now,
      updated_at: now,
    } as Fund & {
      geographies: string[];
      average_investment: string[];
      asset_class: string[];
      contact_name: string | null;
      contact_email: string | null;
      contact_phone: string | null;
    };
  });

  // Sort alphabetically
  funds.sort((a, b) => a.name.localeCompare(b.name));

  // Create the database object
  const db = {
    generated_at: now,
    source: 'AIFI (Associazione Italiana del Private Equity, Venture Capital e Private Debt)',
    pem_manifest: null,
    funds,
    deals: [], // Will be populated from PEM if needed
    signals: [],
  };

  // Write output
  writeFileSync(OUTPUT_PATH, JSON.stringify(db, null, 2));
  console.log(`\nWritten ${funds.length} funds to ${OUTPUT_PATH}`);

  // Print summary stats
  const categoryStats = new Map<string, number>();
  for (const fund of funds) {
    const count = categoryStats.get(fund.category) || 0;
    categoryStats.set(fund.category, count + 1);
  }

  console.log('\nCategory distribution:');
  for (const [cat, count] of Array.from(categoryStats.entries()).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${cat}: ${count}`);
  }
}

main().catch(console.error);
