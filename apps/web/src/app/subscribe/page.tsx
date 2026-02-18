import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';
import { SubscribeForm } from './SubscribeForm';

export const metadata = {
  title: 'Subscribe — PE & VC Signals',
  description: 'Get weekly PE & VC signals on Italian deals, exits, fundraises, and key hires for €9/month.',
};

export default function SubscribePage() {
  const reviews = [
    {
      quote:
        'I use Fundradar to stay on top of the industry and track what competitors are doing without relying on what newspapers choose to publish.',
      author: 'Mid-Market PE Fund Manager',
    },
    {
      quote:
        'Fundradar allows me to anticipate where my support will be most needed, so I can prepare focused materials and deepen my knowledge accordingly.',
      author: 'MBB Consultant',
    },
    {
      quote:
        'Fundradar helps me track where the market is moving and prepare experienced candidate profiles before clients ask for them.',
      author: 'Recruiting Agency Director',
    },
  ];

  return (
    <div style={{ maxWidth: '600px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, margin: '0 0 8px 0', color: '#1a1a2e' }}>
          PE & VC Signals
        </h1>
        <p style={{ fontSize: '15px', color: '#666', margin: '0 0 24px 0' }}>
          Stay ahead with weekly email digests of Italian private equity and venture capital activity.
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

      <div style={{ ...CARD_STYLE, padding: CARD_PADDING, marginTop: '16px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#1a1a2e', margin: '0 0 12px 0' }}>
          What Subscribers Say
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {reviews.map((review) => (
            <div
              key={review.author}
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                background: '#fafafa',
                padding: '12px',
              }}
            >
              <p style={{ margin: 0, fontSize: '14px', color: '#333', lineHeight: 1.5 }}>
                &ldquo;{review.quote}&rdquo;
              </p>
              <p style={{ margin: '8px 0 0 0', fontSize: '12px', color: '#666', fontWeight: 600 }}>
                {review.author}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
