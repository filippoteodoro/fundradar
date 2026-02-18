/**
 * Fund Quality Audit — CLI script
 *
 * Computes data quality scores for all funds and outputs a ranked report.
 * Worst-scoring funds appear first to prioritize data improvement work.
 *
 * Usage: pnpm audit:quality
 *    or: npx tsx scripts/audit-fund-quality.ts
 *
 * Output:
 *   - Formatted table to stdout
 *   - Full JSON report to data/derived/fund_quality_audit.json
 */

import { writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');

// Set cwd to apps/web so getRepoRoot() resolves correctly
process.chdir(join(projectRoot, 'apps', 'web'));

// Dynamic import after chdir — the web lib relies on process.cwd() for path resolution
const { computeAllFundQualities } = await import('../apps/web/src/lib/fundQuality.js');
import type { FundQualityResult, SectionScore } from '../apps/web/src/lib/fundQuality.js';

// ─── Run scoring ────────────────────────────────────────────────────

console.log('Computing fund quality scores...\n');

const results = computeAllFundQualities();
const all = Object.values(results) as FundQualityResult[];

// Sort worst first (ascending)
all.sort((a, b) => a.compositeScore - b.compositeScore);

// ─── Grade distribution ─────────────────────────────────────────────

const grades: Record<string, number> = { A: 0, B: 0, C: 0, D: 0, F: 0 };
for (const r of all) grades[r.grade]++;

console.log('Fund Quality Audit Report');
console.log('=========================\n');
console.log(`Total funds: ${all.length}`);
console.log(`Grade Distribution: A: ${grades.A}  B: ${grades.B}  C: ${grades.C}  D: ${grades.D}  F: ${grades.F}\n`);

// ─── Stats ──────────────────────────────────────────────────────────

const avgScore = all.length > 0
  ? (all.reduce((sum, r) => sum + r.compositeScore, 0) / all.length).toFixed(1)
  : '0';
const medianScore = all.length > 0 ? all[Math.floor(all.length / 2)].compositeScore : 0;
console.log(`Average Score: ${avgScore}  Median Score: ${medianScore}\n`);

// ─── Top red flags ──────────────────────────────────────────────────

const flagCounts: Record<string, number> = {};
for (const r of all) {
  for (const flag of r.redFlags) {
    flagCounts[flag] = (flagCounts[flag] || 0) + 1;
  }
}
const sortedFlags = Object.entries(flagCounts).sort((a, b) => b[1] - a[1]);
console.log('Most Common Red Flags:');
for (const [flag, count] of sortedFlags.slice(0, 10)) {
  console.log(`  ${String(count).padStart(4)} funds  ${flag}`);
}
console.log('');

// ─── Worst 20 table ─────────────────────────────────────────────────

function pad(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + '…' : s.padEnd(n);
}

function rpad(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) : s.padStart(n);
}

const WORST_N = 20;
const worst = all.slice(0, WORST_N);

console.log(`WORST ${WORST_N} FUNDS (prioritize for data improvement):`);
console.log('─'.repeat(120));
console.log(
  `${pad('#', 4)} ${pad('Fund', 32)} ${rpad('Grade', 5)} ${rpad('Score', 5)} ${rpad('Prof', 5)} ${rpad('AIFI', 5)} ${rpad('Port', 5)} ${rpad('Sig', 5)}  Red Flags`
);
console.log('─'.repeat(120));

for (let i = 0; i < worst.length; i++) {
  const r = worst[i];
  const flags = r.redFlags.slice(0, 3).join(', ');
  console.log(
    `${rpad(String(i + 1), 4)} ${pad(r.name, 32)} ${rpad(r.grade, 5)} ${rpad(String(r.compositeScore), 5)} ${rpad(String(r.profileScore.score), 5)} ${rpad(String(r.aifiScore.score), 5)} ${rpad(String(r.portfolioScore.score), 5)} ${rpad(String(r.signalScore.score), 5)}  ${flags}`
  );
}

console.log('─'.repeat(120));

// ─── Best 10 table ──────────────────────────────────────────────────

const BEST_N = 10;
const best = [...all].reverse().slice(0, BEST_N);

console.log(`\nBEST ${BEST_N} FUNDS (reference for data quality standards):`);
console.log('─'.repeat(120));
console.log(
  `${pad('#', 4)} ${pad('Fund', 32)} ${rpad('Grade', 5)} ${rpad('Score', 5)} ${rpad('Prof', 5)} ${rpad('AIFI', 5)} ${rpad('Port', 5)} ${rpad('Sig', 5)}  Red Flags`
);
console.log('─'.repeat(120));

for (let i = 0; i < best.length; i++) {
  const r = best[i];
  const flags = r.redFlags.length > 0 ? r.redFlags.slice(0, 3).join(', ') : '(none)';
  console.log(
    `${rpad(String(i + 1), 4)} ${pad(r.name, 32)} ${rpad(r.grade, 5)} ${rpad(String(r.compositeScore), 5)} ${rpad(String(r.profileScore.score), 5)} ${rpad(String(r.aifiScore.score), 5)} ${rpad(String(r.portfolioScore.score), 5)} ${rpad(String(r.signalScore.score), 5)}  ${flags}`
  );
}

console.log('─'.repeat(120));

// ─── Write full JSON report ─────────────────────────────────────────

const outputPath = join(projectRoot, 'data', 'derived', 'fund_quality_audit.json');

const report = {
  generated_at: new Date().toISOString(),
  total_funds: all.length,
  grade_distribution: grades,
  average_score: parseFloat(avgScore),
  median_score: medianScore,
  top_red_flags: sortedFlags.slice(0, 20).map(([flag, count]) => ({ flag, count })),
  funds: all.map(r => ({
    slug: r.slug,
    name: r.name,
    compositeScore: r.compositeScore,
    grade: r.grade,
    profileScore: r.profileScore.score,
    aifiScore: r.aifiScore.score,
    portfolioScore: r.portfolioScore.score,
    signalScore: r.signalScore.score,
    redFlags: r.redFlags,
    details: {
      profile: r.profileScore.details,
      aifi: r.aifiScore.details,
      portfolio: r.portfolioScore.details,
      signals: r.signalScore.details,
    },
  })),
};

writeFileSync(outputPath, JSON.stringify(report, null, 2));
console.log(`\nFull report written to: ${outputPath}`);
