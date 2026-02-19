import { Suspense } from 'react';
import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';
import { PurchaseEvent } from './PurchaseEvent';
import { LEGAL_BILLING_PORTAL_URL, LEGAL_DIGEST_UNSUBSCRIBE_EMAIL } from '@/lib/legal';

export const metadata = {
  title: 'Subscribed — Fundradar',
};

export default function SubscribeSuccessPage() {
  return (
    <div style={{ maxWidth: '500px', margin: '80px auto', textAlign: 'center' }}>
      <Suspense fallback={null}>
        <PurchaseEvent />
      </Suspense>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>&#10003;</div>
        <h1 style={{ fontSize: '22px', fontWeight: 700, margin: '0 0 12px 0', color: '#1a1a2e' }}>
          You are subscribed
        </h1>
        <p style={{ fontSize: '15px', color: '#666', margin: '0 0 24px 0' }}>
          You will receive weekly signals at your email address.
        </p>
        <p style={{ fontSize: '13px', color: '#666', margin: '0 0 24px 0', lineHeight: 1.5 }}>
          Manage billing or cancel anytime via{' '}
          <a href={LEGAL_BILLING_PORTAL_URL} target="_blank" rel="noopener noreferrer" style={{ color: '#0066cc', textDecoration: 'none' }}>
            Stripe billing portal
          </a>
          . For digest-only opt-out, email{' '}
          {LEGAL_DIGEST_UNSUBSCRIBE_EMAIL ? (
            <a href={`mailto:${LEGAL_DIGEST_UNSUBSCRIBE_EMAIL}`} style={{ color: '#0066cc', textDecoration: 'none' }}>
              {LEGAL_DIGEST_UNSUBSCRIBE_EMAIL}
            </a>
          ) : (
            'our support contact'
          )}
          .
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
