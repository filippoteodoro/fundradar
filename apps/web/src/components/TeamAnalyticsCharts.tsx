'use client';

import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { TeamAnalytics } from '@fundradar/shared';

// Unified dark→light blue gradient. Index 0 = largest value (darkest).
const GRADIENT = ['#1a1a2e', '#0f4c81', '#1565c0', '#1976d2', '#1e88e5', '#42a5f5', '#64b5f6', '#90caf9'];
const colorAt = (i: number) => GRADIENT[Math.min(i, GRADIENT.length - 1)];
const CHART_LABEL_FONT_SIZE = 12;
const HORIZONTAL_BAR_SIZE = 24;
const BAR_ROW_HEIGHT = 34;
const BAR_CHART_MARGIN = { left: 0, right: 30 };
const BAR_LABEL_STYLE = { position: 'right' as const, fill: '#666', fontSize: CHART_LABEL_FONT_SIZE };
const CARD_STYLE = {
  background: '#fafafa',
  borderRadius: '12px',
  padding: '20px',
};
const HEADING_STYLE = { margin: '0 0 16px 0', fontSize: '15px', color: '#333', fontWeight: 600 } as const;
const STAT_ROW_STYLE = {
  margin: 0,
  fontSize: '13px',
  color: '#666',
  display: 'flex',
  alignItems: 'baseline',
  gap: '8px',
  lineHeight: 1.4,
};
const STAT_VALUE_STYLE = {
  color: '#444',
  fontWeight: 600,
  fontVariantNumeric: 'tabular-nums',
};

// School name normalization — merge variants into canonical short names
const SCHOOL_ALIASES: [RegExp, string][] = [
  // Italian
  [/bocconi|sda bocconi/i, 'Bocconi'],
  [/politecnico di milano/i, 'PoliMi'],
  [/politecnico di torino/i, 'PoliTo'],
  [/sapienza|la sapienza/i, 'Sapienza'],
  [/luiss/i, 'LUISS'],
  [/cattolica del sacro cuore|cattolica/i, 'Cattolica'],
  [/ca.? ?foscari/i, "Ca' Foscari"],
  [/studi di milano(?!.*(bicocca|bocconi))/i, 'Univ. Milano'],
  [/bicocca/i, 'Milano-Bicocca'],
  [/alma mater|(?:univ|studi).+bologna/i, 'Univ. Bologna'],
  [/studi di padova|padova/i, 'Univ. Padova'],
  [/studi di torino/i, 'Univ. Torino'],
  [/napoli federico|federico ii/i, 'Federico II'],
  [/studi di firenze|firenze/i, 'Univ. Firenze'],
  [/studi di pavia|pavia/i, 'Univ. Pavia'],
  [/studi di bergamo/i, 'Univ. Bergamo'],
  [/tor vergata/i, 'Tor Vergata'],
  [/liuc/i, 'LIUC'],
  // UK
  [/london business school/i, 'LBS'],
  [/london school of economics|lse/i, 'LSE'],
  [/oxford/i, 'Oxford'],
  [/cambridge/i, 'Cambridge'],
  [/imperial college/i, 'Imperial'],
  [/king'?s college/i, "King's College"],
  [/university college london|\bucl\b/i, 'UCL'],
  [/exeter/i, 'Exeter'],
  // US
  [/harvard/i, 'Harvard'],
  [/wharton/i, 'Wharton'],
  [/stanford/i, 'Stanford'],
  [/mit\b|massachusetts institute|mit sloan/i, 'MIT'],
  [/columbia/i, 'Columbia'],
  [/duke/i, 'Duke'],
  [/chicago/i, 'Univ. Chicago'],
  [/\bucla\b/i, 'UCLA'],
  // Europe
  [/insead/i, 'INSEAD'],
  [/hec paris/i, 'HEC Paris'],
  [/escp/i, 'ESCP'],
  [/edhec/i, 'EDHEC'],
  [/emlyon/i, 'emlyon'],
  [/essec/i, 'ESSEC'],
  [/esade/i, 'ESADE'],
  [/rotterdam|erasmus/i, 'Erasmus'],
  [/maastricht/i, 'Maastricht'],
  [/mannheim/i, 'Mannheim'],
  [/amsterdam/i, 'Amsterdam'],
  [/solvay/i, 'Solvay'],
  [/college of europe/i, 'College of Europe'],
  [/concordia/i, 'Concordia'],
];

function normalizeSchoolName(name: string): string {
  for (const [pattern, canonical] of SCHOOL_ALIASES) {
    if (pattern.test(name)) return canonical;
  }
  // Generic "Università/University degli Studi di X" → "Univ. X"
  const degliMatch = name.match(/(?:universit[àa]|university)\s+degli\s+studi\s+di\s+(.+)/i);
  if (degliMatch) return `Univ. ${degliMatch[1].split(/[,(\-–]/)[0].trim()}`;
  // "University of/di/della X" → "Univ. X"
  const ofMatch = name.match(/^(?:universit[àa]|university)\s+(?:of|di|d[ae]ll[ao']?)\s+(.+)/i);
  if (ofMatch) return `Univ. ${ofMatch[1].split(/[,(\-–]/)[0].trim()}`;
  // Other "University X" or "X University" → strip "University"
  const uniStrip = name.replace(/\s*universit[àa]y?\s*/i, ' ').trim();
  if (uniStrip !== name.trim() && uniStrip.length > 0) return uniStrip.length > 20 ? uniStrip.substring(0, 17) + '...' : uniStrip;
  // Strip common suffixes for brevity
  const cleaned = name.replace(/\s+(business school|school of management|graduate school of business)\s*$/i, '').trim();
  // Shorten long names
  return cleaned.length > 20 ? cleaned.substring(0, 17) + '...' : cleaned;
}

function mergeSchools(schools: Record<string, number>): { name: string; value: number }[] {
  const merged: Record<string, number> = {};
  for (const [name, count] of Object.entries(schools)) {
    const canonical = normalizeSchoolName(name);
    merged[canonical] = (merged[canonical] || 0) + count;
  }
  return Object.entries(merged)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

/** Reusable horizontal bar chart card */
function HBarCard({
  title,
  subtitle,
  data,
  yAxisWidth,
  formatLabel,
}: {
  title: string;
  subtitle?: string;
  data: { name: string; value: number; rawValue: number }[];
  yAxisWidth: number;
  formatLabel: (v: unknown) => string;
}) {
  return (
    <div style={CARD_STYLE}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', margin: '0 0 16px 0' }}>
        <h3 style={{ ...HEADING_STYLE, margin: 0 }}>{title}</h3>
        {subtitle && <span style={{ fontSize: '12px', color: '#999' }}>{subtitle}</span>}
      </div>
      <ResponsiveContainer width="100%" height={data.length * BAR_ROW_HEIGHT + 10}>
        <BarChart data={data} layout="vertical" margin={BAR_CHART_MARGIN}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="name"
            width={yAxisWidth}
            tick={{ fontSize: CHART_LABEL_FONT_SIZE, fill: '#666' }}
            tickLine={false}
            axisLine={false}
          />
          <Bar
            dataKey="value"
            barSize={HORIZONTAL_BAR_SIZE}
            radius={[0, 4, 4, 0]}
            label={{ ...BAR_LABEL_STYLE, formatter: formatLabel }}
          >
            {data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={colorAt(index)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface Props {
  analytics: TeamAnalytics;
  isDummy?: boolean;
}

export function TeamAnalyticsCharts({ analytics, isDummy = false }: Props) {
  // With full HarvestAPI data (has school records), "other" is a real category (media, real estate, etc.)
  // With apimaestro headline-only data (no schools), "other" just means unclassified — hide it.
  const hasRichData = Object.keys(analytics.education.top_schools).length > 0;

  const classifiedBackgrounds = Object.entries(analytics.backgrounds)
    .filter(([name, value]) => name !== 'other' && value > 0);
  const totalBackgrounds = classifiedBackgrounds.reduce((a, [, v]) => a + v, 0);

  const classifiedSeniority = Object.entries(analytics.seniority)
    .filter(([name, value]) => name !== 'other' && value > 0);
  const totalSeniority = classifiedSeniority.reduce((a, [, v]) => a + v, 0);

  // Transform backgrounds data
  const backgroundsData = classifiedBackgrounds
    .map(([name, value]) => ({
      name: name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      value: totalBackgrounds > 0 ? Math.round((value / totalBackgrounds) * 100) : 0,
      rawValue: value,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);

  // Transform seniority data for pie chart (as percentages)
  const seniorityData = classifiedSeniority
    .map(([name, value]) => ({
      name: name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      value: totalSeniority > 0 ? Math.round((value / totalSeniority) * 100) : 0,
      rawValue: value,
    }))
    .sort((a, b) => b.value - a.value);

  const RADIAN = Math.PI / 180;
  const renderSeniorityLabel = ({
    cx,
    cy,
    midAngle,
    innerRadius,
    outerRadius,
    percent,
  }: {
    cx?: number;
    cy?: number;
    midAngle?: number;
    innerRadius?: number;
    outerRadius?: number;
    percent?: number;
  }) => {
    if (cx == null || cy == null || midAngle == null || innerRadius == null || outerRadius == null || percent == null) return null;
    if (percent < 0.02) return null;
    const pctText = `${Math.round(percent * 100)}%`;

    if (percent >= 0.08) {
      // Large slice — label inside
      const radius = innerRadius + (outerRadius - innerRadius) * 0.55;
      const x = cx + radius * Math.cos(-midAngle * RADIAN);
      const y = cy + radius * Math.sin(-midAngle * RADIAN);
      return (
        <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={CHART_LABEL_FONT_SIZE} fontWeight={600}>
          {pctText}
        </text>
      );
    }

    // Small slice — label outside with short connector line
    const cos = Math.cos(-midAngle * RADIAN);
    const sin = Math.sin(-midAngle * RADIAN);
    const mx = cx + (outerRadius + 1) * cos;
    const my = cy + (outerRadius + 1) * sin;
    const ex = cx + (outerRadius + 6) * cos;
    const ey = cy + (outerRadius + 6) * sin;
    const textAnchor = cos >= 0 ? 'start' : 'end';
    return (
      <g>
        <line x1={mx} y1={my} x2={ex} y2={ey} stroke="#999" strokeWidth={1} />
        <text
          x={ex + (cos >= 0 ? 4 : -4)}
          y={ey}
          textAnchor={textAnchor}
          dominantBaseline="central"
          fill="#666"
          fontSize={11}
        >
          {pctText}
        </text>
      </g>
    );
  };

  // Top schools — merge variants, then compute percentages
  const allMergedSchools = mergeSchools(analytics.education.top_schools);
  const mergedSchools = allMergedSchools.slice(0, 6);
  const totalSchools = allMergedSchools.reduce((a, b) => a + b.value, 0);
  const schoolsData = mergedSchools.map(s => ({
    name: s.name,
    value: totalSchools > 0 ? Math.round((s.value / totalSchools) * 100) : 0,
    rawValue: s.value,
  }));

  // Hiring trend data — non-overlapping year buckets
  // Total classified profiles = sum of seniority (same investment-relevant population as hiring counts)
  const totalClassified = Object.values(analytics.seniority).reduce((a, b) => a + b, 0);
  const hires1y = analytics.hiring.new_hires_last_1y;
  const hires1to2 = Math.max(0, analytics.hiring.new_hires_last_2y - hires1y);
  const hires2to3 = Math.max(0, analytics.hiring.new_hires_last_3y - analytics.hiring.new_hires_last_2y);
  const hires3to4 = Math.max(0, analytics.hiring.new_hires_last_4y - analytics.hiring.new_hires_last_3y);
  const hires4plus = Math.max(0, totalClassified - analytics.hiring.new_hires_last_4y);
  const hiringData = [
    { name: '0-1Y', value: hires1y, rawValue: hires1y },
    { name: '1-2Y', value: hires1to2, rawValue: hires1to2 },
    { name: '2-3Y', value: hires2to3, rawValue: hires2to3 },
    { name: '3-4Y', value: hires3to4, rawValue: hires3to4 },
    { name: '4Y+', value: hires4plus, rawValue: hires4plus },
  ];
  const hasHiringVelocityData = totalClassified >= 5;

  // Top majors data — show top 5 only
  const allMajorsEntries = Object.entries(analytics.education.top_majors)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  const majorsEntries = allMajorsEntries.slice(0, 5);
  const totalMajors = Object.values(analytics.education.top_majors).reduce((a, b) => a + b, 0);
  const majorsData = majorsEntries.map(([name, value]) => ({
    name,
    value: totalMajors > 0 ? Math.round((value / totalMajors) * 100) : 0,
    rawValue: value,
  }));
  const hasMajorsData = majorsData.length >= 2 && totalMajors >= 5;

  const hasAverageExperience = analytics.demographics.avg_years_experience > 0;
  const hasAverageTenure = analytics.hiring.avg_tenure_years > 0;

  const pctLabel = (v: unknown) => `${v}%`;
  const countLabel = (v: unknown) => `${v}`;

  return (
    <>
      <div
        className="team-analytics-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '24px',
        }}
      >
        {/* Row 1: Backgrounds | Seniority | Schools */}
        {backgroundsData.length >= 2 && totalBackgrounds >= 5 && (
          <HBarCard
            title="Professional Backgrounds"
            subtitle={classifiedBackgrounds.length > 6 ? 'top 6' : undefined}
            data={backgroundsData}
            yAxisWidth={120}
            formatLabel={pctLabel}
          />
        )}

        {/* Seniority Distribution - Pie Chart */}
        {seniorityData.length >= 2 && totalSeniority >= 5 && (
          <div style={CARD_STYLE}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', margin: '0 0 16px 0' }}>
              <h3 style={{ ...HEADING_STYLE, margin: 0 }}>
                Seniority Distribution
              </h3>
              {seniorityData.length < Object.values(analytics.seniority).filter(v => v > 0).length && (
                <span style={{ fontSize: '12px', color: '#999' }}>top {seniorityData.length}</span>
              )}
            </div>
            <div className="team-analytics-seniority-body" style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div className="team-analytics-seniority-chart">
                <ResponsiveContainer width={180} height={180}>
                  <PieChart>
                    <Pie
                      data={seniorityData}
                      cx="50%"
                      cy="50%"
                      innerRadius={20}
                      outerRadius={60}
                      paddingAngle={2}
                      dataKey="value"
                      labelLine={false}
                      label={renderSeniorityLabel}
                    >
                      {seniorityData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={colorAt(index)} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </div>
              {/* Legend */}
              <div className="team-analytics-seniority-legend" style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
                {seniorityData.map((d, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: `${CHART_LABEL_FONT_SIZE}px` }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ width: '10px', height: '10px', borderRadius: '2px', background: colorAt(i), display: 'inline-block', flexShrink: 0 }} />
                      <span style={{ color: '#444' }}>{d.name}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {(hasAverageExperience || hasAverageTenure) && (
              <div style={{ marginTop: '18px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {hasAverageExperience && (
                  <p style={STAT_ROW_STYLE}>
                    <strong style={{ ...STAT_VALUE_STYLE, minWidth: '88px' }}>
                      {analytics.demographics.avg_years_experience.toFixed(0)} years
                    </strong>
                    <span>average experience</span>
                  </p>
                )}
                {hasAverageTenure && (
                  <p style={STAT_ROW_STYLE}>
                    <strong style={{ ...STAT_VALUE_STYLE, minWidth: '88px' }}>
                      {analytics.hiring.avg_tenure_years.toFixed(1)} years
                    </strong>
                    <span>average tenure</span>
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {schoolsData.length >= 2 && totalSchools >= 5 && (
          <HBarCard
            title="Top Schools"
            subtitle={allMergedSchools.length > 6 ? 'top 6' : undefined}
            data={schoolsData}
            yAxisWidth={140}
            formatLabel={pctLabel}
          />
        )}

        {/* Row 2: Hiring Velocity | Top Majors — centered */}
        {(hasHiringVelocityData || hasMajorsData) && (
          <div className="team-analytics-secondary-row" style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'center', gap: '24px' }}>
            {hasHiringVelocityData && (
              <div className="team-analytics-secondary-card" style={{ flex: '0 1 calc((100% - 48px) / 3)' }}>
                <HBarCard
                  title="Hiring Velocity"
                  data={hiringData}
                  yAxisWidth={40}
                  formatLabel={countLabel}
                />
              </div>
            )}
            {hasMajorsData && (
              <div className="team-analytics-secondary-card" style={{ flex: '0 1 calc((100% - 48px) / 3)' }}>
                <HBarCard
                  title="Top Majors"
                  subtitle={allMajorsEntries.length > 5 ? 'top 5' : undefined}
                  data={majorsData}
                  yAxisWidth={100}
                  formatLabel={pctLabel}
                />
              </div>
            )}
          </div>
        )}
      </div>
      <style jsx>{`
        @media (max-width: 1100px) {
          .team-analytics-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
          }

          .team-analytics-secondary-card {
            flex: 1 1 calc((100% - 24px) / 2) !important;
          }
        }

        @media (max-width: 768px) {
          .team-analytics-grid {
            grid-template-columns: 1fr !important;
            gap: 16px !important;
          }

          .team-analytics-secondary-row {
            flex-direction: column !important;
            align-items: stretch !important;
            justify-content: flex-start !important;
            gap: 16px !important;
          }

          .team-analytics-secondary-card {
            flex: 1 1 auto !important;
            width: 100% !important;
          }

          .team-analytics-seniority-body {
            flex-direction: column !important;
            align-items: stretch !important;
            gap: 12px !important;
          }

          .team-analytics-seniority-chart {
            display: flex !important;
            justify-content: center !important;
          }

          .team-analytics-seniority-legend {
            width: 100% !important;
          }
        }
      `}</style>
    </>
  );
}
