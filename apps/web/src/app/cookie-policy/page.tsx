import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import { CookiePreferenceReset } from '@/components/CookiePreferenceReset';

export const metadata: Metadata = {
  title: 'Cookie Policy',
  description: 'Cookie policy for Fundradar.',
  alternates: { canonical: '/cookie-policy' },
};

const LAST_UPDATED = 'February 19, 2026';

export default function CookiePolicyPage() {
  return (
    <div style={{ maxWidth: '760px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Cookie Policy</h1>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. What this policy covers</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            This page explains how Fundradar uses cookies and similar technologies (local storage,
            measurement tags, and anti-spam tokens).
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Consent model</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            On first visit we ask you to accept or reject non-essential tracking. Essential security
            and login cookies stay enabled because they are required to operate the service. Consent
            preference is stored for up to 6 months, then requested again.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Technologies we use</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>
              <strong>Essential cookie</strong>: `fundradar_session` (session/authentication, up to
              7 days).
            </li>
            <li>
              <strong>Consent preference storage</strong>: `fundradar_cookie_consent_v1` (local
              storage, up to 6 months).
            </li>
            <li>
              <strong>Optional analytics and conversion tracking</strong>: Google Tag Manager,
              Google Analytics, LinkedIn Insight Tag, and Vercel Analytics (only when consented).
            </li>
            <li>
              <strong>Anti-spam protection</strong>: Google reCAPTCHA tokens for contact-form abuse
              prevention.
            </li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Third-party providers</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Cookie or tag-related processing may involve Google (Tag Manager, Analytics, reCAPTCHA),
            LinkedIn (Insight Tag), Stripe, and Vercel.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Manage your choices</h2>
          <p style={{ margin: '0 0 10px 0', lineHeight: 1.6, color: '#444' }}>
            You can re-open the cookie choice prompt at any time:
          </p>
          <CookiePreferenceReset />
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. More information</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            For details on how personal data is processed and your rights, see our{' '}
            <Link href="/privacy-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Privacy Policy
            </Link>.
          </p>
        </section>
      </div>
    </div>
  );
}
