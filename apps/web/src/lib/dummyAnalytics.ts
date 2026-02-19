/**
 * Generate dummy team analytics data for preview
 */

import type { TeamAnalytics } from '@fundradar/shared';

export function generateDummyAnalytics(fundSlug: string): TeamAnalytics {
  // Seed random based on slug for consistency
  const seed = fundSlug.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const rand = (min: number, max: number) => min + ((seed * 9301 + 49297) % 233280) / 233280 * (max - min);

  const totalProfiles = Math.floor(rand(15, 45));

  return {
    fund_slug: fundSlug,
    total_profiles: totalProfiles,
    education: {
      top_schools: {
        'Bocconi University': Math.floor(rand(3, 10)),
        'Politecnico di Milano': Math.floor(rand(2, 6)),
        'INSEAD': Math.floor(rand(1, 4)),
        'London Business School': Math.floor(rand(1, 4)),
        'Harvard Business School': Math.floor(rand(0, 3)),
        'Stanford GSB': Math.floor(rand(0, 2)),
      },
      top_degrees: {
        'MBA': Math.floor(rand(5, 15)),
        'Finance': Math.floor(rand(3, 10)),
        'Economics': Math.floor(rand(3, 8)),
        'Engineering': Math.floor(rand(2, 6)),
      },
      top_majors: {
        'Finance': Math.floor(rand(5, 15)),
        'Economics': Math.floor(rand(4, 12)),
        'Management': Math.floor(rand(3, 10)),
        'Engineering': Math.floor(rand(2, 8)),
        'Law': Math.floor(rand(1, 5)),
      },
      education_tier: {
        top_mba: Math.floor(rand(5, 15)),
        top_undergrad: Math.floor(rand(8, 20)),
        other: Math.floor(rand(5, 15)),
      },
    },
    backgrounds: {
      private_equity: Math.floor(rand(8, 20)),
      investment_banking: Math.floor(rand(5, 15)),
      consulting: Math.floor(rand(3, 10)),
      big_four: Math.floor(rand(2, 6)),
      corporate: Math.floor(rand(1, 5)),
      tech: Math.floor(rand(0, 3)),
    },
    seniority: {
      partner: Math.floor(rand(3, 8)),
      managing_director: Math.floor(rand(2, 5)),
      director: Math.floor(rand(3, 7)),
      principal: Math.floor(rand(2, 6)),
      vice_president: Math.floor(rand(2, 5)),
      associate: Math.floor(rand(4, 10)),
      analyst: Math.floor(rand(2, 6)),
      other: Math.floor(rand(0, 3)),
    },
    hiring: {
      new_hires_last_1y: Math.floor(rand(2, 8)),
      new_hires_last_2y: Math.floor(rand(5, 15)),
      new_hires_last_3y: Math.floor(rand(8, 22)),
      new_hires_last_4y: Math.floor(rand(12, 30)),
      avg_tenure_years: parseFloat(rand(2.5, 5.5).toFixed(1)),
    },
    demographics: {
      gender_male_pct: parseFloat(rand(60, 80).toFixed(1)),
      gender_female_pct: parseFloat(rand(20, 40).toFixed(1)),
      gender_unknown_pct: parseFloat(rand(0, 10).toFixed(1)),
      avg_years_experience: parseFloat(rand(8, 18).toFixed(1)),
      avg_estimated_age: parseFloat(rand(32, 45).toFixed(1)),
    },
  };
}
