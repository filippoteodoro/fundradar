import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';
import { SubscribeForm } from './SubscribeForm';
import { loadUnifiedSignals } from '@/lib/signals_unified';
import { SignalCard } from '@/components/SignalCard';
import { toDisplayType, SIGNAL_TYPE_IMPORTANCE } from '@/lib/signalProcessing';
import type { UnifiedSignal } from '@/lib/signals_unified';

export const metadata = {
  title: 'Subscribe — PE & VC Signals',
  description: 'Get weekly PE & VC signals on Italian deals, exits, fundraises, and key hires for €9/month.',
};

function isCompellingSignal(s: UnifiedSignal): boolean {
  const sa = s as any;

  if (sa.quality_score != null && sa.quality_score < 85) return false;

  // Exclude signals the relevance scorer explicitly flagged as not Italy-relevant
  if (sa.italy_relevant === false) return false;

  const text = s.what_changed || s.title || '';

  // Require substantial text — short titles are nav artifacts or truncated
  if (text.length < 80) return false;

  // Reject pipe-separated navigation artifacts ("Entity | Section")
  if (/ \| /.test(text)) return false;

  // Require a confirmed event date
  if (!s.published_at) return false;

  // Exclude signals older than 90 days
  const daysSince = (Date.now() - new Date(s.published_at).getTime()) / (1000 * 60 * 60 * 24);
  if (daysSince > 90) return false;

  // Exclude vague/unclassified signals and job postings — not compelling for conversion
  if (s.signal_type === 'other' || s.signal_type === 'job_posting') return false;

  return true;
}

/** Extract monetary value from signal text in millions of euros. */
function extractAmountMillions(text: string): number {
  if (!text) return 0;
  let maxAmount = 0;
  const p1 = /[€$£]\s*(\d+(?:[.,]\d+)?)\s*(?:m(?:illion|ln|io)?|b(?:illion|n|rd)?)\b/gi;
  let match;
  while ((match = p1.exec(text)) !== null) {
    const num = parseFloat(match[1].replace(',', '.'));
    if (isNaN(num) || num <= 0) continue;
    const isBillion = /b(?:illion|n|rd)?/i.test(match[0]);
    maxAmount = Math.max(maxAmount, isBillion ? num * 1000 : num);
  }
  const p2 = /(\d+(?:[.,]\d+)?)\s+(?:m(?:illion|ln|io)|b(?:illion|n|rd))\w*\s*(?:[€$£]|eur(?:o|os)?|usd|gbp)/gi;
  while ((match = p2.exec(text)) !== null) {
    const num = parseFloat(match[1].replace(',', '.'));
    if (isNaN(num) || num <= 0) continue;
    const isBillion = /b(?:illion|n|rd)/i.test(match[0]);
    maxAmount = Math.max(maxAmount, isBillion ? num * 1000 : num);
  }
  return maxAmount;
}

function getSampleScore(s: UnifiedSignal): number {
  const sa = s as any;

  // Signal type importance (0–15)
  const typePts = SIGNAL_TYPE_IMPORTANCE[s.signal_type] || 0;

  // Recency: exponential decay with ~14-day half-life
  // Today → +30, 14 days → +15, 30 days → +7, 60 days → +1.5
  const ts = s.published_at ? new Date(s.published_at).getTime() : 0;
  const daysSince = ts > 0 ? (Date.now() - ts) / (1000 * 60 * 60 * 24) : 999;
  const recencyScore = 30 * Math.exp(-daysSince / 14);

  // Deal size bonus — log-scaled: €10M→10, €100M→20, €1B→30
  const text = s.what_changed || s.title || '';
  const amountM = extractAmountMillions(text);
  const amountBonus = amountM > 0 ? Math.max(0, Math.log10(amountM)) * 10 : 0;

  // Enriched summary bonus — these display more context and look more polished
  const enrichedBonus = sa.enriched_summary ? 8 : 0;

  // Italy relevance bonus
  const italyBonus = sa.italy_relevant === true ? 5 : 0;

  return typePts + recencyScore + amountBonus + enrichedBonus + italyBonus;
}

function pickSampleSignals(signals: UnifiedSignal[]): UnifiedSignal[] {
  const candidates = signals
    .filter(isCompellingSignal)
    .sort((a, b) => getSampleScore(b) - getSampleScore(a));

  const picked: UnifiedSignal[] = [];
  // At most 1 signal per display type to maximise variety across 3 slots
  const typeCounts = new Map<string, number>();

  for (const s of candidates) {
    if (picked.length >= 3) break;
    const displayType = toDisplayType(s.signal_type);
    if ((typeCounts.get(displayType) ?? 0) >= 1) continue;
    picked.push(s);
    typeCounts.set(displayType, (typeCounts.get(displayType) ?? 0) + 1);
  }

  // If strict variety left fewer than 3, backfill allowing a second per type
  if (picked.length < 3) {
    const pickedIds = new Set(picked.map((s) => s.id));
    for (const s of candidates) {
      if (picked.length >= 3) break;
      if (pickedIds.has(s.id)) continue;
      const displayType = toDisplayType(s.signal_type);
      if ((typeCounts.get(displayType) ?? 0) >= 2) continue;
      picked.push(s);
      pickedIds.add(s.id);
      typeCounts.set(displayType, (typeCounts.get(displayType) ?? 0) + 1);
    }
  }

  // Display newest first
  return picked.sort((a, b) => new Date(b.published_at!).getTime() - new Date(a.published_at!).getTime());
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
          Stay ahead with weekly email digests of Italian funds activity. With agentic coding PE/VC databases have no
          reason to cost €X000/month.
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
          <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#1a1a2e', margin: '0 0 16px 0' }}>
            Sample signals from our feed
          </h2>
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
          What subscribers say
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
