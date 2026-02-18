'use client';

import type { Signal } from '@fundradar/shared';
import { formatDate } from '@/lib/formatDate';
import { CARD_STYLE, CARD_PADDING, badgeStyle, RUMOR_STYLE } from '@/lib/ui';
import { toDisplayType, SIGNAL_TYPE_STYLES } from '@/lib/signalProcessing';

interface SignalCardProps {
  signal: Signal & { fund_name?: string; fund_slug?: string; is_rumor?: boolean };
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
          {signal.is_rumor && (
            <span style={badgeStyle(RUMOR_STYLE)}>{RUMOR_STYLE.label}</span>
          )}
          {showFundLink && (signal as any).fund_slug && (
            <a
              href={`/funds/${(signal as any).fund_slug}`}
              style={{ color: '#0066cc', textDecoration: 'none', fontWeight: 500 }}
            >
              {(signal as any).fund_name}
            </a>
          )}
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
            style={{ color: '#0066cc' }}
          >
            {getSourceDisplayName(signal.source_url, signal.source_name)}
          </a>
        )}
      </div>
    </div>
  );
}
