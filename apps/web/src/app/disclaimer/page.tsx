import type { Metadata } from 'next';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';

export const metadata: Metadata = {
  title: 'Disclaimer',
  description: 'Important legal disclaimers for Fundradar.',
  alternates: { canonical: '/disclaimer' },
};

const LAST_UPDATED = 'February 19, 2026';

export default function DisclaimerPage() {
  return (
    <div style={{ maxWidth: '760px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Disclaimer</h1>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. No investment advice</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Fundradar does not provide investment advice, recommendations, solicitations, or
            endorsements of any security, fund, manager, or transaction.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Public-source information</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Data is derived from publicly available sources and is provided on an &quot;as is&quot;
            and &quot;as available&quot; basis. We do not warrant completeness, accuracy, or
            suitability for any purpose.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Independent verification</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            You are responsible for independently verifying any information before relying on it for
            business, legal, financial, or investment decisions.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Third-party content</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            External links and third-party content are provided for convenience. Fundradar is not
            responsible for third-party websites, terms, or privacy practices.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Liability</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            To the maximum extent permitted by law, Fundradar disclaims liability for losses or
            damages resulting from use of the website or reliance on its contents.
          </p>
        </section>
      </div>
    </div>
  );
}
