import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import { CookiePreferenceReset } from '@/components/CookiePreferenceReset';

export const metadata: Metadata = {
  title: 'Cookie Policy',
  description: 'Cookie policy for Fundradar.',
  alternates: { canonical: '/cookie-policy' },
};

const LAST_UPDATED = 'September 21, 2026';

export default function CookiePolicyPage() {
  return (
    <div style={{ maxWidth: '780px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Cookie Policy</h1>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Consent</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            On your first visit, we ask whether you accept optional analytics cookies. Google Tag
            Manager and Google Analytics load only after you accept. We store your choice for up to
            6 months, then ask again.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Technologies in use</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>
              <strong>Consent choice</strong> (essential): `fundradar_cookie_consent_v1` in local
              storage, up to 6 months.
            </li>
            <li>
              <strong>Banner dismissal</strong> (essential): `fundradar_beta_banner_dismissed`
              cookie, until midnight of the same day.
            </li>
            <li>
              <strong>Analytics</strong> (optional, consent only): Google Tag Manager and Google
              Analytics cookies.
            </li>
            <li>
              <strong>Cookieless analytics</strong>: Vercel Analytics and Speed Insights collect
              aggregate data without cookies.
            </li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Manage your choice</h2>
          <p style={{ margin: '0 0 10px 0', lineHeight: 1.6, color: '#444' }}>
            You can re-open the cookie prompt and change your choice at any time:
          </p>
          <CookiePreferenceReset />
          <p style={{ margin: '12px 0 0 0', lineHeight: 1.6, color: '#444' }}>
            You can also delete cookies through your browser settings.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. More information</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            See the{' '}
            <Link href="/privacy-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Privacy Policy
            </Link>
            .
          </p>
        </section>
      </div>
    </div>
  );
}
