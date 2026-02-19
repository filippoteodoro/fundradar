import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import { CookiePreferenceReset } from '@/components/CookiePreferenceReset';
import { LEGAL_BUNDLE_VERSION } from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Cookie Policy',
  description: 'Cookie policy for Fundradar.',
  alternates: { canonical: '/cookie-policy' },
};

const LAST_UPDATED = 'February 19, 2026';

export default function CookiePolicyPage() {
  return (
    <div style={{ maxWidth: '780px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Cookie Policy</h1>
        <p style={{ margin: '0 0 8px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Legal bundle version: {LEGAL_BUNDLE_VERSION}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Scope</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            This policy explains how Fundradar uses cookies and similar technologies (local storage,
            measurement tags, and anti-spam tokens) under EU and Italian cookie rules.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Consent model</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            On first visit, we ask whether you accept optional analytics and conversion tracking.
            Essential technologies remain enabled because they are required for service security and
            functionality.
          </p>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Consent preference is stored for up to 6 months, then requested again.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Technologies in use</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>
              <strong>Essential authentication/session cookie</strong>: `fundradar_session` (up to 7
              days).
            </li>
            <li>
              <strong>Consent preference storage</strong>: `fundradar_cookie_consent_v1` (local
              storage, up to 6 months).
            </li>
            <li>
              <strong>Optional analytics/conversion tracking</strong>: Google Tag Manager, Google
              Analytics, LinkedIn Insight Tag, and Vercel Analytics (only when consented).
            </li>
            <li>
              <strong>Security / anti-spam</strong>: Google reCAPTCHA tokens for contact-form abuse
              prevention.
            </li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Purposes and legal basis</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Essential security and login operations: legitimate interest / strict necessity.</li>
            <li>Optional analytics and conversion measurement: consent.</li>
            <li>Anti-spam verification: legitimate interest in service integrity.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Third-party providers</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            Cookie or tag-related processing may involve Google (Tag Manager, Analytics,
            reCAPTCHA), LinkedIn (Insight Tag), Stripe (checkout flow), and Vercel (hosting and
            analytics infrastructure).
          </p>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Provider policies and transfer safeguards are handled in our{' '}
            <Link href="/privacy-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Privacy Policy
            </Link>
            .
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. Manage your choices</h2>
          <p style={{ margin: '0 0 10px 0', lineHeight: 1.6, color: '#444' }}>
            You can re-open the cookie prompt and update your choice at any time:
          </p>
          <CookiePreferenceReset />
          <p style={{ margin: '12px 0 0 0', lineHeight: 1.6, color: '#444' }}>
            You can also manage cookies through your browser settings. Disabling essential cookies
            may affect login and core functionality.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>7. Changes to this policy</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We may update this policy to reflect legal, technical, or operational changes. The date
            and legal bundle version above indicate the currently applicable version.
          </p>
        </section>
      </div>
    </div>
  );
}
