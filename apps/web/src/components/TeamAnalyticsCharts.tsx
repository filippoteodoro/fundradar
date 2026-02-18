'use client';

import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { TeamAnalytics } from '@fundradar/shared';

// Unified dark→light blue gradient. Index 0 = largest value (darkest).
const GRADIENT = ['#1a1a2e', '#0f4c81', '#1565c0', '#1976d2', '#1e88e5', '#42a5f5', '#64b5f6', '#90caf9'];
const colorAt = (i: number) => GRADIENT[Math.min(i, GRADIENT.length - 1)];
const CHART_LABEL_FONT_SIZE = 12;
const HORIZONTAL_BAR_SIZE = 24;
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
  [/bocconi|sda bocconi/i, 'Bocconi'],
  [/politecnico di milano/i, 'Politecnico di Milano'],
  [/politecnico di torino/i, 'Politecnico di Torino'],
  [/sapienza|la sapienza/i, 'Sapienza Roma'],
  [/luiss/i, 'LUISS'],
  [/harvard/i, 'Harvard'],
  [/wharton/i, 'Wharton'],
  [/insead/i, 'INSEAD'],
  [/london business school/i, 'LBS'],
  [/london school of economics|lse/i, 'LSE'],
  [/oxford/i, 'Oxford'],
  [/cambridge/i, 'Cambridge'],
  [/stanford/i, 'Stanford'],
  [/mit|massachusetts institute/i, 'MIT'],
  [/columbia/i, 'Columbia'],
  [/università cattolica|cattolica del sacro cuore/i, 'Cattolica'],
  [/università degli studi di milano(?! bicocca)/i, 'Univ. Milano'],
  [/bicocca/i, 'Milano-Bicocca'],
  [/bologna/i, 'Univ. Bologna'],
  [/padova/i, 'Univ. Padova'],
  [/napoli federico/i, 'Federico II Napoli'],
  [/ca' foscari|ca foscari/i, "Ca' Foscari"],
  [/imperial college/i, 'Imperial College'],
];

function normalizeSchoolName(name: string): string {
  for (const [pattern, canonical] of SCHOOL_ALIASES) {
    if (pattern.test(name)) return canonical;
  }
  // Shorten long names
  return name.length > 25 ? name.substring(0, 22) + '...' : name;
}

function mergeSchools(schools: Record<string, number>): { name: string; value: number }[] {
  const merged: Record<string, number> = {};
  for (const [name, count] of Object.entries(schools)) {
    const canonical = normalizeSchoolName(name);
    merged[canonical] = (merged[canonical] || 0) + count;
  }
  return Object.entries(merged)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
}

interface Props {
  analytics: TeamAnalytics;
  isDummy?: boolean;
}

export function TeamAnalyticsCharts({ analytics, isDummy = false }: Props) {
  // Exclude "other" — it means unclassified, not a real background/seniority category.
  // Percentages are computed against classified-only totals so bars sum to 100%.
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
    if (percent < 0.08) return null;
    const radius = innerRadius + (outerRadius - innerRadius) * 0.55;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);

    return (
      <text
        x={x}
        y={y}
        fill="white"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={CHART_LABEL_FONT_SIZE}
        fontWeight={600}
      >
        {`${Math.round(percent * 100)}%`}
      </text>
    );
  };

  // Top schools — merge variants, then compute percentages
  const mergedSchools = mergeSchools(analytics.education.top_schools);
  const totalSchools = mergedSchools.reduce((a, b) => a + b.value, 0);
  const schoolsData = mergedSchools.map(s => ({
    name: s.name,
    value: totalSchools > 0 ? Math.round((s.value / totalSchools) * 100) : 0,
    rawValue: s.value,
  }));

  // Hiring trend data — show non-overlapping periods (2Y is cumulative, includes 1Y)
  const hires1y = analytics.hiring.new_hires_last_1y;
  const hiresPriorYear = Math.max(0, analytics.hiring.new_hires_last_2y - hires1y);
  const hiringData = [
    { name: '0-1Y', value: hires1y },
    { name: '1-2Y', value: hiresPriorYear },
  ];
  const hasHiringVelocityData = analytics.hiring.new_hires_last_1y > 0 || analytics.hiring.new_hires_last_2y > 0;
  const hasAverageExperience = analytics.demographics.avg_years_experience > 0;
  const hasAverageTenure = analytics.hiring.avg_tenure_years > 0;

  return (
    <div>
      {/* Charts Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: '24px',
      }}>
        {/* Professional Backgrounds - Horizontal Bar Chart */}
        {backgroundsData.length > 0 && totalBackgrounds >= 3 && (
        <div style={{
          background: '#fafafa',
          borderRadius: '12px',
          padding: '20px',
        }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '15px', color: '#333', fontWeight: 600 }}>
            Professional Backgrounds
          </h3>
          <ResponsiveContainer width="100%" height={backgroundsData.length * 34 + 10}>
            <BarChart data={backgroundsData} layout="vertical" margin={{ left: 0, right: 20 }}>
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="name"
                width={120}
                tick={{ fontSize: CHART_LABEL_FONT_SIZE, fill: '#666' }}
                tickLine={false}
                axisLine={false}
              />
              <Bar dataKey="value" barSize={HORIZONTAL_BAR_SIZE} radius={[0, 4, 4, 0]} label={{ position: 'right', fill: '#666', fontSize: CHART_LABEL_FONT_SIZE, formatter: (v: unknown) => `${v}%` }}>
                {backgroundsData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={colorAt(index)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        )}

        {/* Seniority Distribution - Pie Chart with Legend */}
        {seniorityData.length > 0 && totalSeniority >= 3 && (
        <div style={{
          background: '#fafafa',
          borderRadius: '12px',
          padding: '20px',
        }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '15px', color: '#333', fontWeight: 600 }}>
            Seniority Distribution
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <ResponsiveContainer width={140} height={140}>
              <PieChart>
                <Pie
                  data={seniorityData}
                  cx="50%"
                  cy="50%"
                  innerRadius={20}
                  outerRadius={65}
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
            {/* Legend */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
              {seniorityData.slice(0, 6).map((d, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: `${CHART_LABEL_FONT_SIZE}px` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ width: '10px', height: '10px', borderRadius: '2px', background: colorAt(i), display: 'inline-block', flexShrink: 0 }} />
                    <span style={{ color: '#444' }}>{d.name}</span>
                  </div>
                </div>
              ))}
              {seniorityData.length > 6 && (
                <div style={{ fontSize: `${CHART_LABEL_FONT_SIZE}px`, color: '#999' }}>+{seniorityData.length - 6} more</div>
              )}
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

        {/* Top Schools - Horizontal Bar Chart */}
        {schoolsData.length > 0 && (
        <div style={{
          background: '#fafafa',
          borderRadius: '12px',
          padding: '20px',
        }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '15px', color: '#333', fontWeight: 600 }}>
            Top Schools
          </h3>
          <ResponsiveContainer width="100%" height={schoolsData.length * 40 + 10}>
            <BarChart data={schoolsData} layout="vertical" margin={{ left: 0, right: 30 }}>
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="name"
                width={140}
                tick={{ fontSize: CHART_LABEL_FONT_SIZE, fill: '#666' }}
                tickLine={false}
                axisLine={false}
              />
              <Bar dataKey="value" barSize={HORIZONTAL_BAR_SIZE} radius={[0, 4, 4, 0]} label={{ position: 'right', fill: '#666', fontSize: CHART_LABEL_FONT_SIZE, formatter: (v: unknown) => `${v}%` }}>
                {schoolsData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={colorAt(index)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        )}
      </div>

      {/* Hiring Velocity Bar */}
      {hasHiringVelocityData && (
        <div style={{
          background: '#fafafa',
          borderRadius: '12px',
          padding: '20px',
          marginTop: '24px',
        }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '15px', color: '#333', fontWeight: 600 }}>
            Hiring Velocity
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '32px', flexWrap: 'wrap', rowGap: '14px' }}>
            <ResponsiveContainer width={260} height={80}>
              <BarChart data={hiringData} layout="vertical" margin={{ right: 24 }}>
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={36}
                  tick={{ fontSize: CHART_LABEL_FONT_SIZE, fill: '#666' }}
                  tickLine={false}
                  axisLine={false}
                />
                <Bar
                  dataKey="value"
                  barSize={HORIZONTAL_BAR_SIZE}
                  radius={[0, 4, 4, 0]}
                  label={{ position: 'right', fill: '#444', fontSize: CHART_LABEL_FONT_SIZE, formatter: (v: unknown) => `${v}` }}
                >
                  {hiringData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={colorAt(index)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div
              style={{
                flex: '1 1 220px',
                minWidth: '220px',
                minHeight: '80px',
                display: 'grid',
                gridTemplateRows: '1fr 1fr',
                rowGap: '4px',
                alignItems: 'center',
              }}
            >
              <p style={STAT_ROW_STYLE}>
                <span>joined last 12 months</span>
              </p>
              <p style={STAT_ROW_STYLE}>
                <span>joined 1–2 years ago</span>
              </p>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
