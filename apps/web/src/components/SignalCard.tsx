'use client';

import type { Signal } from '@fundradar/shared';
import { formatDate } from '@/lib/formatDate';
import { CARD_STYLE, CARD_PADDING, badgeStyle, RUMOR_STYLE } from '@/lib/ui';
import { toDisplayType, SIGNAL_TYPE_STYLES } from '@/lib/signalProcessing';

interface SignalCardProps {
  signal: Signal & {
    fund_name?: string;
    fund_slug?: string;
    related_fund_slugs?: string[];
    related_fund_names?: string[];
    is_rumor?: boolean;
  };
  /** Show fund name as a link (used on /signals page, not on fund detail page) */
  showFundLink?: boolean;
}

/** Extract a friendly source name from URL — show full path, not just domain */
function getSourceDisplayName(sourceUrl: string, sourceName: string): string {
  if (sourceName !== 'Website Monitor') {
    return sourceName;
  }
  try {
    const url = new URL(sourceUrl);
    const domain = url.hostname.replace(/^www\./, '');
    const path = url.pathname === '/' ? '' : url.pathname;
    return domain + path;
  } catch {
    return sourceName;
  }
}

export function SignalCard({ signal, showFundLink = false }: SignalCardProps) {
  const displayType = toDisplayType(signal.signal_type);
  const typeStyle = SIGNAL_TYPE_STYLES[displayType] || SIGNAL_TYPE_STYLES.other;

  const dateLabel = signal.published_at
    ? formatDate(signal.published_at)
    : `${formatDate(signal.observed_at)} (observed)`;

  const primaryText = signal.what_changed || signal.title || '';
  const relatedFundSlugs = (signal.related_fund_slugs || []).filter(Boolean);
  const relatedFundNames = signal.related_fund_names || [];
  const fundTags =
    relatedFundSlugs.length > 0
      ? relatedFundSlugs.map((slug, idx) => ({
          slug,
          name: relatedFundNames[idx] || slug.replace(/-/g, ' '),
        }))
      : ((signal as any).fund_slug
          ? [{
              slug: (signal as any).fund_slug as string,
              name: (signal as any).fund_name as string || ((signal as any).fund_slug as string).replace(/-/g, ' '),
            }]
          : []);

  return (
    <div
      style={{
        ...CARD_STYLE,
        padding: CARD_PADDING,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={badgeStyle(typeStyle)}>{typeStyle.label}</span>
          {(signal as any).signal_types?.slice(1).map((st: string) => {
            const secStyle = SIGNAL_TYPE_STYLES[toDisplayType(st as Parameters<typeof toDisplayType>[0])] ?? SIGNAL_TYPE_STYLES.other;
            if (secStyle === typeStyle) return null;
            return (
              <span key={st} style={{ ...badgeStyle(secStyle), opacity: 0.75 }}>
                {secStyle.label}
              </span>
            );
          })}
          {signal.is_rumor && (
            <span style={badgeStyle(RUMOR_STYLE)}>{RUMOR_STYLE.label}</span>
          )}
          {showFundLink && fundTags.map((fund, idx) => (
            <span key={`${fund.slug}-${idx}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
              {idx > 0 && <span style={{ color: '#999' }}>•</span>}
              <a
                href={`/funds/${fund.slug}`}
                style={{ color: '#1976d2', textDecoration: 'none', fontWeight: 500 }}
              >
                {fund.name}
              </a>
            </span>
          ))}
        </div>
        <span
          style={{
            fontSize: '13px',
            whiteSpace: 'nowrap',
            color: signal.published_at ? '#666' : '#999',
            fontStyle: signal.published_at ? 'normal' : 'italic',
          }}
          title={signal.published_at
            ? `Observed: ${formatDate(signal.observed_at)}`
            : 'No event date available; showing when we first detected this signal'}
        >
          {dateLabel}
        </span>
      </div>
      {primaryText && (
        <p style={{ margin: '8px 0 6px 0', fontWeight: 400, color: '#222' }}>
          {primaryText}
        </p>
      )}
      <div style={{ fontSize: '13px', color: '#666' }}>
        Source:{' '}
        {signal.source_url_status === 'unavailable' ? (
          <span style={{ color: '#999' }}>
            {getSourceDisplayName(signal.source_url, signal.source_name)}{' '}
            <span style={{ fontStyle: 'italic' }}>(unavailable)</span>
          </span>
        ) : (
          <a
            href={signal.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#1976d2' }}
          >
            {getSourceDisplayName(signal.source_url, signal.source_name)}
          </a>
        )}
      </div>
    </div>
  );
}
