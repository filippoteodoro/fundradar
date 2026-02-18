import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';

export const metadata = {
  title: 'Subscribed — Fundradar',
};

export default function SubscribeSuccessPage() {
  return (
    <div style={{ maxWidth: '500px', margin: '80px auto', textAlign: 'center' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>&#10003;</div>
        <h1 style={{ fontSize: '22px', fontWeight: 700, margin: '0 0 12px 0', color: '#1a1a2e' }}>
          You are subscribed
        </h1>
        <p style={{ fontSize: '15px', color: '#666', margin: '0 0 24px 0' }}>
          You will receive weekly signals at your email address.
        </p>
        <a
          href="/"
          style={{
            display: 'inline-block',
            padding: '10px 24px',
            background: '#1a1a2e',
            color: 'white',
            textDecoration: 'none',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: 600,
          }}
        >
          Browse Funds
        </a>
      </div>
    </div>
  );
}
