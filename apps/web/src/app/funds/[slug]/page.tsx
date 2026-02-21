import type { Metadata } from 'next';
import dynamic from 'next/dynamic';
import {
  getAllFunds,
  getFundBySlug,
  getSignalsForFund,
  getPortfolioForFund,
  getPortfolioNote,
  getTeamAnalyticsForFund,
  isManualLinkedinProfileFund,
  getSortedOffices,
} from '@/lib/data';
import { notFound } from 'next/navigation';
import type { Fund, FundCategory, TeamAnalytics, Office } from '@fundradar/shared';
import { FUND_CATEGORY_LABELS } from '@fundradar/shared';
const TeamAnalyticsCharts = dynamic(
  () => import('@/components/TeamAnalyticsCharts').then(mod => ({ default: mod.TeamAnalyticsCharts })),
  { ssr: false }
);
import { PortfolioSection } from '@/components/PortfolioSection';
import { SignalsCompact } from '@/components/SignalsCompact';
import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';
import { CATEGORY_COLORS } from '@/lib/colors';
import { formatAum } from '@/lib/fundRangeFilters';
import { fundSectorGroups, getSectorGroupColor } from '@/lib/sectorGroups';

export function generateStaticParams() {
  return getAllFunds().map((f) => ({ slug: f.slug }));
}

export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const fund = getFundBySlug(slug);
  if (!fund) return { title: 'Fund Not Found', robots: { index: false } };

  const sectors = fund.sector_tags.slice(0, 3).join(', ');
  const category = FUND_CATEGORY_LABELS[fund.category];
  const location = fund.hq_city || 'Italy';
  const description = fund.description
    || `${fund.name} is a ${category.toLowerCase()} fund based in ${location}${sectors ? ` investing in ${sectors}` : ''}.`;

  return {
    title: fund.name,
    description: description.slice(0, 160),
    openGraph: {
      title: `${fund.name} — ${category}`,
      description: description.slice(0, 200),
      type: 'website',
      url: `/funds/${fund.slug}`,
    },
    alternates: {
      canonical: `/funds/${fund.slug}`,
    },
  };
}

type ExtendedFund = Fund & {
  geographies?: string[];
  average_investment?: string[];
  asset_class?: string[];
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  data_sources?: string[];
  data_confidence?: string | null;
  // AIFI metrics
  aum_eur?: number | null;
  num_funds?: number | null;
  num_portfolio_companies?: number | null;
  num_executives?: number | null;
  num_sfdr_article_8?: number | null;
  investment_min_eur?: number | null;
  investment_max_eur?: number | null;
  aifi_url?: string | null;
  aifi_scraped_at?: string | null;
};

function formatInvestmentRange(min: number | null | undefined, max: number | null | undefined): string | null {
  if (!min && !max) return null;
  const formatAmount = (n: number) => {
    if (n >= 1e9) {
      const v = n / 1e9;
      return v >= 5 ? `€${Math.round(v / 5) * 5}B` : `€${+v.toFixed(1)}B`;
    }
    if (n >= 1e6) {
      const v = n / 1e6;
      return v >= 5 ? `€${Math.round(v / 5) * 5}M` : `€${+v.toFixed(1)}M`;
    }
    if (n >= 1e3) return `€${Math.round(n / 1e3)}K`;
    return `€${n}`;
  };
  if (min && max) return `${formatAmount(min)} - ${formatAmount(max)}`;
  if (min) return `From ${formatAmount(min)}`;
  if (max) return `Up to ${formatAmount(max)}`;
  return null;
}

function formatTagLabel(tag: string): string {
  return tag.replace(/-/g, ' ');
}

function formatSourceLabel(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function isInvalidContactValue(value: string | null | undefined): boolean {
  if (!value) return true;
  const trimmed = value.trim();
  if (!trimmed || trimmed === '-') return true;
  const lower = trimmed.toLowerCase();
  return lower.startsWith('javascript:') || lower.includes('__dopostback');
}

function normalizeContactName(value: string | null | undefined): string | null {
  if (isInvalidContactValue(value)) return null;
  return value!.trim();
}

function normalizeContactEmail(value: string | null | undefined): string | null {
  if (isInvalidContactValue(value)) return null;
  let email = value!.trim();
  const lower = email.toLowerCase();
  if (lower.startsWith('mailto:')) {
    email = email.slice('mailto:'.length);
  }
  if (lower.startsWith('http://') || lower.startsWith('https://')) return null;

  const candidates = email
    .split(/[;,\\s]+/)
    .map((part) => part.trim())
    .filter(Boolean);

  for (const candidate of candidates) {
    if (/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(candidate)) {
      return candidate;
    }
  }
  return null;
}

function normalizeContactPhone(value: string | null | undefined): string | null {
  if (isInvalidContactValue(value)) return null;
  let trimmed = value!.trim();
  if (trimmed.toLowerCase().startsWith('tel:')) {
    trimmed = trimmed.slice('tel:'.length).trim();
  }
  return /\\d/.test(trimmed) ? trimmed : null;
}

export default async function FundPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const baseFund = getFundBySlug(slug);

  if (!baseFund) {
    notFound();
  }

  const fund = baseFund as ExtendedFund;
  const signals = getSignalsForFund(slug);
  const portfolioCompanies = getPortfolioForFund(slug);
  const portfolioNote = getPortfolioNote(slug);
  const teamAnalytics = getTeamAnalyticsForFund(slug);
  // Italy-only note is driven by manual_profiles.json, not by mega-fund membership.
  const hasManualLinkedinProfiles = !!teamAnalytics && isManualLinkedinProfileFund(slug);
  const contactName = normalizeContactName(fund.contact_name);
  const contactEmail = normalizeContactEmail(fund.contact_email);
  const contactPhone = normalizeContactPhone(fund.contact_phone);
  const hasContact = Boolean(contactName || contactEmail || contactPhone);
  const offices = getSortedOffices(fund);
  const sourceUrls = Array.from(new Set(fund.data_sources || []))
    .filter(Boolean)
    .filter((url) => !/aifi/i.test(url)) as string[];

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: fund.name,
    ...(fund.website ? { url: fund.website } : {}),
    ...(fund.description ? { description: fund.description } : {}),
    ...(fund.hq_city ? {
      address: {
        '@type': 'PostalAddress',
        addressLocality: fund.hq_city,
        addressCountry: 'IT',
      },
    } : {}),
  };

  return (
    <div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <a href="/" style={{ color: '#0066cc', textDecoration: 'none', fontSize: '14px' }}>
        ← Back to all funds
      </a>

      <div
        style={{
          ...CARD_STYLE,
          padding: CARD_PADDING,
          marginTop: '16px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
          <h1 style={{ margin: 0 }}>{fund.name}</h1>
          <a
            href="/about#contact"
            style={{ color: '#888', textDecoration: 'none', fontSize: '13px', whiteSpace: 'nowrap', marginTop: '6px' }}
          >
            Submit feedback
          </a>
        </div>
        <div
          className="fund-detail-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: hasContact
              ? 'minmax(180px, 1fr) minmax(360px, 2fr) minmax(180px, 1fr)'
              : 'minmax(200px, 1fr) minmax(420px, 2fr)',
            gap: '16px',
            marginBottom: '16px',
          }}
        >
          <div>
            <p style={{ margin: '0 0 6px 0', fontSize: '12px', color: '#888', fontWeight: 600 }}>Website</p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {fund.website ? (
                <a
                  href={fund.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#0066cc', textDecoration: 'none', fontSize: '14px' }}
                >
                  {formatSourceLabel(fund.website)}
                </a>
              ) : (
                <span style={{ color: '#999' }}>-</span>
              )}
              {fund.linkedin_url && (
                <a
                  href={fund.linkedin_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="LinkedIn"
                  style={{ color: '#0a66c2', textDecoration: 'none', fontSize: '14px', display: 'inline-flex', alignItems: 'center' }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                  </svg>
                </a>
              )}
            </div>
          </div>

          <div>
            <p style={{ margin: '0 0 6px 0', fontSize: '12px', color: '#888', fontWeight: 600 }}>Address</p>
            {offices.length > 0 ? (
              <div>
                {offices.map((office, i) => (
                  <div key={i} style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    gap: '8px',
                    flexWrap: 'wrap',
                    marginBottom: i < offices.length - 1 ? '6px' : 0,
                  }}>
                    <span style={{ color: '#333', fontWeight: 400 }}>
                      {office.address ? `${office.address}, ` : ''}
                      {office.postal_code ? `${office.postal_code} ` : ''}
                      {office.city}, {office.country}
                    </span>
                    {office.is_hq && (
                      <span style={{
                        background: '#e3f2fd',
                        color: '#1565c0',
                        padding: '1px 6px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        fontWeight: 600,
                      }}>
                        HQ
                      </span>
                    )}
                    {office.source_url && office.source_name && (
                      <a
                        href={office.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: '#999', fontSize: '11px', textDecoration: 'none' }}
                        aria-label={office.source_name}
                        title={office.source_name}
                      >
                        Source
                      </a>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <span style={{ color: '#666' }}>{fund.hq_city || 'Location unknown'}</span>
            )}
          </div>

          {(contactName || contactEmail || contactPhone) && (
            <div>
              <p style={{ margin: '0 0 6px 0', fontSize: '12px', color: '#888', fontWeight: 600 }}>Contact</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {contactName && (
                  <span style={{ color: '#333' }}>{contactName}</span>
                )}
                {contactEmail && (
                  <a href={`mailto:${contactEmail}`} style={{ color: '#0066cc' }}>{contactEmail}</a>
                )}
                {contactPhone && (
                  <span style={{ color: '#333' }}>{contactPhone}</span>
                )}
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
          <span
            style={{
              background: CATEGORY_COLORS[fund.category].bg,
              color: CATEGORY_COLORS[fund.category].text,
              padding: '4px 12px',
              borderRadius: '4px',
              fontSize: '14px',
              fontWeight: 500,
            }}
          >
            {FUND_CATEGORY_LABELS[fund.category]}
          </span>
          {fundSectorGroups(fund.sector_tags).length > 0 && (
            <>
              <span style={{ color: '#ccc', fontSize: '16px', userSelect: 'none' }} aria-hidden="true">|</span>
              {fundSectorGroups(fund.sector_tags).map((groupName) => {
                const color = getSectorGroupColor(groupName);
                return (
                  <span
                    key={groupName}
                    style={{
                      background: color.bg,
                      color: color.text,
                      padding: '4px 12px',
                      borderRadius: '4px',
                      fontSize: '14px',
                    }}
                  >
                    {groupName}
                  </span>
                );
              })}
            </>
          )}
        </div>

        {fund.description && (
          <p style={{ margin: '0 0 0 0', color: '#333', fontWeight: 400 }}>
            {fund.description}
          </p>
        )}

        {/* Key Metrics from AIFI */}
        {(fund.aum_eur || fund.num_funds || fund.num_executives) && (
          <div style={{
            marginTop: '24px',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: '16px',
            background: '#f8fafc',
            padding: '20px',
            borderRadius: '12px',
          }}>
            {fund.aum_eur && (
              <div style={{ textAlign: 'center' }}>
                <p style={{ margin: 0, fontSize: '24px', fontWeight: 600, color: '#1a1a2e' }}>
                  {formatAum(fund.aum_eur)}
                </p>
                <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#666' }}>AUM</p>
              </div>
            )}
            {fund.num_funds && (
              <div style={{ textAlign: 'center' }}>
                <p style={{ margin: 0, fontSize: '24px', fontWeight: 600, color: '#0f4c81' }}>
                  {fund.num_funds}
                </p>
                <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#666' }}>Funds</p>
              </div>
            )}
            {fund.num_executives && (
              <div style={{ textAlign: 'center' }}>
                <p style={{ margin: 0, fontSize: '24px', fontWeight: 600, color: '#1976d2' }}>
                  {fund.num_executives}
                </p>
                <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#666' }}>Executives</p>
              </div>
            )}
            {fund.num_sfdr_article_8 != null && fund.num_sfdr_article_8 > 0 && (
              <div style={{ textAlign: 'center' }} title="SFDR Article 8 compliant funds promoting environmental/social characteristics">
                <p style={{ margin: 0, fontSize: '24px', fontWeight: 600, color: '#42a5f5' }}>
                  {fund.num_sfdr_article_8}
                </p>
                <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#666' }}>Green Funds</p>
              </div>
            )}
          </div>
        )}

        {/* AIFI Extended Info */}
        <div style={{ marginTop: '24px', paddingTop: '24px', borderTop: '1px solid #eee' }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', color: '#333' }}>Investment Profile</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            {(fund.investment_min_eur || fund.investment_max_eur) && (
              <div>
                <p style={{ margin: '0 0 4px 0', fontSize: '13px', color: '#888', fontWeight: 500 }}>Investment Range</p>
                <p style={{ margin: 0, color: '#333' }}>
                  {formatInvestmentRange(fund.investment_min_eur, fund.investment_max_eur)}
                </p>
              </div>
            )}
            {(() => {
              const st = (fund.strategy_tags || []);
              const ac = (fund.asset_class || []);
              const norm = (s: string) => s.toLowerCase().replace(/-/g, ' ').trim();
              // Tags that duplicate the fund category badge already shown above
              const CATEGORY_REDUNDANT: Record<string, string[]> = {
                pe:           ['private equity'],
                vc:           ['venture capital'],
                growth:       ['growth equity', 'growth capital'],
                infra:        ['infrastructure'],
                debt:         ['private debt', 'credit'],
                real_estate:  ['real estate'],
              };
              const redundant = new Set<string>(CATEGORY_REDUNDANT[fund.category] ?? []);
              const seen = new Set<string>();
              const merged: string[] = [];
              for (const v of [...st, ...ac]) {
                const key = norm(v);
                if (!seen.has(key) && !redundant.has(key)) {
                  seen.add(key);
                  merged.push(formatTagLabel(v));
                }
              }
              if (merged.length === 0) return null;
              return (
                <div>
                  <p style={{ margin: '0 0 4px 0', fontSize: '13px', color: '#888', fontWeight: 500 }}>Focus</p>
                  <p style={{ margin: 0, color: '#333' }}>{merged.join(', ')}</p>
                </div>
              );
            })()}
            {fund.geographies && fund.geographies.length > 0 && (
              <div>
                <p style={{ margin: '0 0 4px 0', fontSize: '13px', color: '#888', fontWeight: 500 }}>Geographies</p>
                <p style={{ margin: 0, color: '#333' }}>{fund.geographies.join(', ')}</p>
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Assets Section */}
      <PortfolioSection companies={portfolioCompanies} emptyNote={portfolioNote} compact />

      {/* Team Analytics Section — only shown when real data exists and sample is meaningful */}
      {teamAnalytics && teamAnalytics.total_profiles >= 5 && (
        <>
          <h2 style={{ marginTop: '32px', marginBottom: '16px' }}>
            People Analytics
            <span style={{ fontSize: '14px', fontWeight: 400, color: '#999', marginLeft: '10px' }}>
              n={teamAnalytics.total_profiles}
              {hasManualLinkedinProfiles && (
                <span style={{ marginLeft: '8px' }}>· Italy team</span>
              )}
            </span>
          </h2>
          <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
            <TeamAnalyticsCharts analytics={teamAnalytics} />
          </div>
        </>
      )}

      {/* Signals Section */}
      {signals.length > 0 && (
        <>
          <h2 style={{ marginTop: '32px', marginBottom: '16px' }}>Signals ({signals.length})</h2>
          <SignalsCompact signals={signals} />
        </>
      )}
    </div>
  );
}
