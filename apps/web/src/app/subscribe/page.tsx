import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';
import { SubscribeForm } from './SubscribeForm';
import { loadUnifiedSignals } from '@/lib/signals_unified';
import { SignalCard } from '@/components/SignalCard';
import { toDisplayType } from '@/lib/signalProcessing';
import type { UnifiedSignal } from '@/lib/signals_unified';

export const metadata = {
  title: 'Subscribe — PE & VC Signals',
  description: 'Get weekly PE & VC signals on Italian deals, exits, fundraises, and key hires for €9/month.',
};

function isCompellingSignal(s: UnifiedSignal): boolean {
  const sa = s as any;

  if (sa.quality_score != null && sa.quality_score < 80) return false;

  // Exclude signals the relevance scorer explicitly flagged as not Italy-relevant
  if (sa.italy_relevant === false) return false;

  const text = s.what_changed || s.title || '';

  // Require meaningful text — short titles are nav artifacts or truncated
  if (text.length < 55) return false;

  // Reject pipe-separated navigation artifacts ("Entity | Section")
  if (/ \| /.test(text)) return false;

  // Require a confirmed event date — real dates rank above observed-only
  if (!s.published_at) return false;

  // Exclude inherently vague/unclassified signals — not compelling for conversion
  if (s.signal_type === 'other') return false;

  return true;
}

const OBSERVED_ONLY_PENALTY_MS = 60 * 60 * 1000;

function getSignalTs(s: UnifiedSignal): number {
  if (s.published_at) return new Date(s.published_at).getTime();
  const raw = s.observed_at || '';
  return raw ? new Date(raw).getTime() - OBSERVED_ONLY_PENALTY_MS : 0;
}

function pickSampleSignals(signals: UnifiedSignal[]): UnifiedSignal[] {
  // signals is already date-sorted by loadUnifiedSignals; re-sort here for safety
  const candidates = signals
    .filter(isCompellingSignal)
    .sort((a, b) => getSignalTs(b) - getSignalTs(a));

  const picked: UnifiedSignal[] = [];
  const usedIds = new Set<string>();
  // Allow at most 2 signals per display type so we get variety without forcing
  // a fixed type order — date remains the primary sort key
  const typeCounts = new Map<string, number>();

  for (const s of candidates) {
    if (picked.length >= 5) break;
    const displayType = toDisplayType(s.signal_type);
    if ((typeCounts.get(displayType) ?? 0) >= 2) continue;
    picked.push(s);
    usedIds.add(s.id);
    typeCounts.set(displayType, (typeCounts.get(displayType) ?? 0) + 1);
  }

  return picked;
}

export default async function SubscribePage() {
  const reviews = [
    {
      quote:
        'I use Fundradar to stay on top of the industry and track what competitors are doing without relying on what newspapers choose to publish.',
      role: 'Investment Manager',
      company: 'Mid-market PE fund, Milan',
      initials: 'MD',
    },
    {
      quote:
        'Fundradar allows me to anticipate where my support will be most needed, so I can prepare focused materials and deepen my knowledge accordingly.',
      role: 'Consultant',
      company: 'MBB, Milan',
      initials: 'GR',
    },
    {
      quote:
        'Fundradar helps me track where the market is moving and prepare experienced candidate profiles before clients ask for them.',
      role: 'Director',
      company: 'Recruiting agency, Rome',
      initials: 'AB',
    },
  ];

  let sampleSignals: UnifiedSignal[] = [];
  try {
    const { signals } = loadUnifiedSignals();
    sampleSignals = pickSampleSignals(signals);
  } catch {
    // If signals fail to load, the section is simply hidden
  }

  return (
    <div style={{ maxWidth: '600px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, margin: '0 0 8px 0', color: '#1a1a2e' }}>
          Get Signals
        </h1>
        <p style={{ fontSize: '15px', color: '#666', margin: '0 0 24px 0' }}>
          Stay ahead with weekly email digests of Italian private equity and venture capital activity.{' '}
          <a href="/signals" style={{ color: '#0066cc', textDecoration: 'none' }}>
            Browse the live signals feed →
          </a>
        </p>

        <div style={{ marginBottom: '24px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '32px',
            fontWeight: 700,
            color: '#1a1a2e',
          }}>
            €9
            <span style={{ fontSize: '15px', fontWeight: 400, color: '#888' }}>/month</span>
          </div>
          <p style={{ fontSize: '13px', color: '#888', margin: '4px 0 0 0' }}>Cancel anytime</p>
        </div>

        <ul style={{
          listStyle: 'none',
          padding: 0,
          margin: '0 0 28px 0',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}>
          {[
            'New deals and investments',
            'Portfolio exits and IPOs',
            'Fund launches and fundraises',
            'Key hires and leadership changes',
            'Weekly digest delivered to your inbox',
            'Request custom features',
          ].map((item) => (
            <li key={item} style={{ fontSize: '14px', color: '#444', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ color: '#2d7a4f', fontWeight: 700, fontSize: '16px' }}>&#10003;</span>
              {item}
            </li>
          ))}
        </ul>

        <SubscribeForm />

        <p style={{
          fontSize: '12px',
          color: '#aaa',
          textAlign: 'center',
          margin: '20px 0 0 0',
        }}>
          Payments processed securely by Stripe. You can cancel your subscription at any time.
        </p>
      </div>

      {sampleSignals.length > 0 && (
        <div style={{ ...CARD_STYLE, padding: CARD_PADDING, marginTop: '16px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#1a1a2e', margin: '0 0 4px 0' }}>
            Recent signals from our feed
          </h2>
          <p style={{ fontSize: '13px', color: '#888', margin: '0 0 16px 0' }}>
            A sample of what subscribers receive each week.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {sampleSignals.map((signal) => (
              <SignalCard key={signal.id} signal={signal} showFundLink={true} />
            ))}
          </div>
          <p style={{ margin: '16px 0 0 0', textAlign: 'center' }}>
            <a href="/signals" style={{ fontSize: '14px', color: '#0066cc', textDecoration: 'none' }}>
              See all signals on the feed →
            </a>
          </p>
        </div>
      )}

      <div style={{ ...CARD_STYLE, padding: CARD_PADDING, marginTop: '16px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#1a1a2e', margin: '0 0 16px 0' }}>
          What Subscribers Say
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {reviews.map((review) => (
            <div
              key={review.role}
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                background: '#fafafa',
                padding: '16px',
              }}
            >
              <p style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#333', lineHeight: 1.6 }}>
                &ldquo;{review.quote}&rdquo;
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{
                  width: '34px',
                  height: '34px',
                  borderRadius: '50%',
                  background: '#1a1a2e',
                  color: 'white',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '11px',
                  fontWeight: 700,
                  flexShrink: 0,
                  letterSpacing: '0.5px',
                }}>
                  {review.initials}
                </div>
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#1a1a2e' }}>{review.role}</div>
                  <div style={{ fontSize: '12px', color: '#888' }}>{review.company}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
