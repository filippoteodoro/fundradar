import type { CSSProperties } from 'react';

export const CARD_RADIUS = '12px';
export const CARD_BORDER = '1px solid #eee';
export const CARD_PADDING = '24px';

export const CARD_STYLE: CSSProperties = {
  background: 'white',
  border: CARD_BORDER,
  borderRadius: CARD_RADIUS,
};

// ── Badge theme ─────────────────────────────────────────────────────────────
// Single source of truth for all badge/tag/pill styling across the app.
// Every badge uses BADGE_STYLE as base, then adds color from its config.

type BadgeColor = { bg: string; color: string };

/** Base style shared by every badge in the app */
export const BADGE_STYLE: CSSProperties = {
  padding: '2px 8px',
  borderRadius: '4px',
  fontSize: '12px',
  whiteSpace: 'nowrap',
};

/** Apply badge colors to base style */
export function badgeStyle(colors: BadgeColor): CSSProperties {
  return { ...BADGE_STYLE, background: colors.bg, color: colors.color };
}

// ── Portfolio status badges ─────────────────────────────────────────────────

export const STATUS_STYLES: Record<string, { label: string } & BadgeColor> = {
  current: { label: 'Current', bg: '#e8f5e9', color: '#2e7d32' },
  partial: { label: 'Partial', bg: '#e3f2fd', color: '#1565c0' },
  exited:  { label: 'Exited',  bg: '#fff3e0', color: '#e65100' },
  unknown: { label: 'Unknown', bg: '#f5f5f5', color: '#757575' },
};

// ── Portfolio data source badges ────────────────────────────────────────────

export const SOURCE_STYLES: Record<string, { label: string } & BadgeColor> = {
  pem:     { label: 'PEM',     bg: '#e8eaf6', color: '#3949ab' },
  news:    { label: 'News',    bg: '#e3f2fd', color: '#1565c0' },
  website: { label: 'Website', bg: '#e8f5e9', color: '#2e7d32' },
  unknown: { label: 'Unknown', bg: '#f5f5f5', color: '#757575' },
};

// ── Signal page category badges ─────────────────────────────────────────────

export const PAGE_CATEGORY_STYLES: Record<string, { label: string } & BadgeColor> = {
  HOME:      { label: 'Home',      bg: '#e0f7fa', color: '#00838f' },
  NEWS:      { label: 'News',      bg: '#fff8e1', color: '#f57f17' },
  PORTFOLIO: { label: 'Portfolio', bg: '#e8f5e9', color: '#2e7d32' },
  TEAM:      { label: 'Team',      bg: '#f3e5f5', color: '#7b1fa2' },
  CAREERS:   { label: 'Careers',   bg: '#fce4ec', color: '#c2185b' },
  OTHER:     { label: 'Other',     bg: '#f5f5f5', color: '#616161' },
};

// ── Rumor badge ─────────────────────────────────────────────────────────────

export const RUMOR_STYLE: { label: string } & BadgeColor = {
  label: 'Rumor', bg: '#ffebee', color: '#d50000',
};

// ── Portfolio sort helpers ───────────────────────────────────────────────────

/** Sort order for portfolio company status. 'unknown' defaults to 2 at call sites. */
export const PORTFOLIO_STATUS_ORDER: Record<string, number> = {
  current: 0,
  partial: 1,
  exited: 3,
};

/** True when a portfolio entry has no usable source attribution. */
export function isUnknownSource(company: { source_label?: string | null; source_url?: string | null }): boolean {
  const normalizedLabel = company.source_label?.trim().toLowerCase() || '';
  if (normalizedLabel === 'unknown') return true;
  return !company.source_url && !normalizedLabel;
}
