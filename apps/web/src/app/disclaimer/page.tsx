import type { Metadata } from 'next';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import { LEGAL_BUNDLE_VERSION } from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Disclaimer',
  description: 'Important legal disclaimers for Fundradar.',
  alternates: { canonical: '/disclaimer' },
};

const LAST_UPDATED = 'February 19, 2026';

export default function DisclaimerPage() {
  return (
    <div style={{ maxWidth: '780px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Disclaimer</h1>
        <p style={{ margin: '0 0 8px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Legal bundle version: {LEGAL_BUNDLE_VERSION}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. No investment recommendation</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Fundradar does not provide investment advice or personalized recommendations. Nothing on
            the website should be interpreted as a solicitation to buy or sell securities or fund
            interests.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Public-source data limits</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Data is compiled from publicly available sources and is provided on an &quot;as is&quot;
            and &quot;as available&quot; basis. We do not guarantee completeness, timeliness,
            accuracy, or fitness for a specific purpose.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Independent verification required</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Users remain responsible for independent due diligence and verification before making
            business, legal, tax, financial, or investment decisions.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Third-party links and services</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            External websites and services are provided for convenience only. Fundradar is not
            responsible for third-party content, security, availability, terms, or privacy
            practices.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. No guarantee of uninterrupted service</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We do not warrant that the service will be uninterrupted, error-free, or permanently
            available. Access may be limited for maintenance, security, infrastructure, or
            third-party dependency reasons.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. Liability limits</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            To the maximum extent permitted by law, Fundradar disclaims liability for direct or
            indirect losses resulting from website use, data inaccuracies, downtime, or reliance on
            published information. Mandatory legal protections remain unaffected.
          </p>
        </section>
      </div>
    </div>
  );
}
