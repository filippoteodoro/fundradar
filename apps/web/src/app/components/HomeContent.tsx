'use client';

import { useState, useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import type { TeamAnalytics } from '@fundradar/shared';
import type { FundSlim } from '@/lib/data';
import type { UnifiedSignal } from '@/lib/signals_unified';
import { FundsTable } from './FundsTable';
import { HomeSignalsSnapshot } from './HomeSignalsSnapshot';
import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';

const TeamAnalyticsCharts = dynamic(
  () => import('@/components/TeamAnalyticsCharts').then(mod => ({ default: mod.TeamAnalyticsCharts })),
  {
    ssr: false,
    loading: () => (
      <div style={{ padding: '40px', textAlign: 'center', color: '#999' }}>
        Loading charts...
      </div>
    ),
  },
);

interface HomeContentProps {
  funds: FundSlim[];
  portfolioCompanyNames: Record<string, string[]>;
  realAnalytics: Record<string, TeamAnalytics>;
  // Source of truth for Italy-only profile coverage note.
  manualLinkedinProfileFundSlugs: string[];
  recentSignals: UnifiedSignal[];
}

function aggregateAnalytics(
  slugs: string[],
  realAnalytics: Record<string, TeamAnalytics>,
): { aggregate: TeamAnalytics; fundCount: number } {
  const backgrounds: Record<string, number> = {};
  const seniority: Record<string, number> = {};
  const schools: Record<string, number> = {};
  const degrees: Record<string, number> = {};
  const majors: Record<string, number> = {};
  let totalProfiles = 0;
  let totalNewHires1y = 0;
  let totalNewHires2y = 0;
  let totalNewHires3y = 0;
  let totalNewHires4y = 0;
  let sumTenure = 0;
  let sumExperience = 0;
  let sumAge = 0;
  let sumMalePct = 0;
  let sumFemalePct = 0;
  let sumUnknownPct = 0;
  let sumTopMba = 0;
  let sumTopUndergrad = 0;
  let sumOtherEdu = 0;
  let fundCount = 0;

  for (const slug of slugs) {
    if (!realAnalytics[slug]) continue;

    const analytics: TeamAnalytics = realAnalytics[slug];

    totalProfiles += analytics.total_profiles;
    totalNewHires1y += analytics.hiring.new_hires_last_1y;
    totalNewHires2y += analytics.hiring.new_hires_last_2y;
    totalNewHires3y += analytics.hiring.new_hires_last_3y;
    totalNewHires4y += analytics.hiring.new_hires_last_4y;
    sumTenure += analytics.hiring.avg_tenure_years;
    sumExperience += analytics.demographics.avg_years_experience;
    sumAge += analytics.demographics.avg_estimated_age;
    sumMalePct += analytics.demographics.gender_male_pct;
    sumFemalePct += analytics.demographics.gender_female_pct;
    sumUnknownPct += analytics.demographics.gender_unknown_pct;
    sumTopMba += analytics.education.education_tier.top_mba;
    sumTopUndergrad += analytics.education.education_tier.top_undergrad;
    sumOtherEdu += analytics.education.education_tier.other;

    for (const [key, val] of Object.entries(analytics.backgrounds)) {
      backgrounds[key] = (backgrounds[key] || 0) + val;
    }
    for (const [key, val] of Object.entries(analytics.seniority)) {
      seniority[key] = (seniority[key] || 0) + val;
    }
    for (const [key, val] of Object.entries(analytics.education.top_schools)) {
      schools[key] = (schools[key] || 0) + val;
    }
    for (const [key, val] of Object.entries(analytics.education.top_degrees)) {
      degrees[key] = (degrees[key] || 0) + val;
    }
    for (const [key, val] of Object.entries(analytics.education.top_majors || {})) {
      majors[key] = (majors[key] || 0) + val;
    }
    fundCount++;
  }

  const sortedSchools = Object.fromEntries(
    Object.entries(schools).sort(([, a], [, b]) => b - a)
  );
  const sortedDegrees = Object.fromEntries(
    Object.entries(degrees).sort(([, a], [, b]) => b - a).slice(0, 6)
  );
  const sortedMajors = Object.fromEntries(
    Object.entries(majors).sort(([, a], [, b]) => b - a)
  );

  const aggregate: TeamAnalytics = {
    fund_slug: 'aggregate',
    total_profiles: totalProfiles,
    education: {
      top_schools: sortedSchools,
      top_degrees: sortedDegrees,
      top_majors: sortedMajors,
      education_tier: {
        top_mba: sumTopMba,
        top_undergrad: sumTopUndergrad,
        other: sumOtherEdu,
      },
    },
    backgrounds,
    seniority,
    hiring: {
      new_hires_last_1y: totalNewHires1y,
      new_hires_last_2y: totalNewHires2y,
      new_hires_last_3y: totalNewHires3y,
      new_hires_last_4y: totalNewHires4y,
      avg_tenure_years: fundCount > 0 ? parseFloat((sumTenure / fundCount).toFixed(1)) : 0,
    },
    demographics: {
      gender_male_pct: fundCount > 0 ? parseFloat((sumMalePct / fundCount).toFixed(1)) : 0,
      gender_female_pct: fundCount > 0 ? parseFloat((sumFemalePct / fundCount).toFixed(1)) : 0,
      gender_unknown_pct: fundCount > 0 ? parseFloat((sumUnknownPct / fundCount).toFixed(1)) : 0,
      avg_years_experience: fundCount > 0 ? parseFloat((sumExperience / fundCount).toFixed(1)) : 0,
      avg_estimated_age: fundCount > 0 ? parseFloat((sumAge / fundCount).toFixed(1)) : 0,
    },
  };

  return { aggregate, fundCount };
}

export function HomeContent({
  funds,
  portfolioCompanyNames,
  realAnalytics,
  manualLinkedinProfileFundSlugs,
  recentSignals,
}: HomeContentProps) {
  const manualLinkedinProfileFundSlugsSet = useMemo(
    () => new Set(manualLinkedinProfileFundSlugs),
    [manualLinkedinProfileFundSlugs],
  );
  const fundNamesBySlug = useMemo(() => {
    const map: Record<string, string> = {};
    for (const f of funds) map[f.slug] = f.name;
    return map;
  }, [funds]);
  const allSlugs = useMemo(() => funds.map(f => f.slug), [funds]);
  const [filteredSlugs, setFilteredSlugs] = useState<string[]>(allSlugs);

  const handleFilteredFundsChange = useCallback((slugs: string[]) => {
    setFilteredSlugs(slugs);
  }, []);

  const { aggregate, fundCount } = useMemo(
    () => aggregateAnalytics(filteredSlugs, realAnalytics),
    [filteredSlugs, realAnalytics],
  );

  const includedManualLinkedinProfileFunds = useMemo(() =>
    filteredSlugs
      .filter(s => manualLinkedinProfileFundSlugsSet.has(s) && !!realAnalytics[s])
      .map(s => fundNamesBySlug[s] || s),
    [filteredSlugs, manualLinkedinProfileFundSlugsSet, realAnalytics, fundNamesBySlug],
  );

  const includedManualLinkedinProfileFundsLabel = useMemo(
    () => [...includedManualLinkedinProfileFunds].sort((a, b) => a.localeCompare(b)).join(', '),
    [includedManualLinkedinProfileFunds],
  );

  const isFiltered = filteredSlugs.length < allSlugs.length;
  const filteredSlugsSet = useMemo(() => new Set(filteredSlugs), [filteredSlugs]);

  return (
    <>
      <FundsTable
        funds={funds}
        portfolioCompanyNames={portfolioCompanyNames}
        onFilteredFundsChange={handleFilteredFundsChange}
      />

      {fundCount > 0 && (
        <div style={{ marginTop: '48px' }}>
          <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>
            People Analytics
            <span style={{ fontSize: '14px', fontWeight: 400, color: '#999', marginLeft: '10px' }}>
              n={aggregate.total_profiles}
            </span>
          </h2>
          <p style={{ margin: '0 0 16px 0', color: '#666', fontSize: '14px' }}>
            Aggregate view across {fundCount} fund{fundCount !== 1 ? 's' : ''}
            {isFiltered ? ` (filtered from ${allSlugs.length})` : ''}
          </p>
          <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
            <TeamAnalyticsCharts analytics={aggregate} />
            {includedManualLinkedinProfileFunds.length > 0 && (
              <p style={{ margin: '10px 0 0 0', color: '#666', fontSize: '13px' }}>
                For the following large global funds, we only included Italian profiles to ensure data is relevant for Italy: {includedManualLinkedinProfileFundsLabel}.
              </p>
            )}
          </div>
        </div>
      )}

      {recentSignals.length > 0 && (
        <HomeSignalsSnapshot signals={recentSignals} filteredSlugSet={filteredSlugsSet} />
      )}
    </>
  );
}
