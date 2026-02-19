import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import {
  LEGAL_CONTROLLER_ADDRESS,
  LEGAL_CONTROLLER_EMAIL,
  LEGAL_CONTROLLER_NAME,
} from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Privacy policy for Fundradar.',
  alternates: { canonical: '/privacy-policy' },
};

const LAST_UPDATED = 'February 19, 2026';

export default function PrivacyPolicyPage() {
  return (
    <div style={{ maxWidth: '760px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Privacy Policy</h1>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Data controller</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            The data controller is <strong>{LEGAL_CONTROLLER_NAME}</strong>.
            <br />
            Contact:{' '}
            {LEGAL_CONTROLLER_EMAIL ? (
              <a href={`mailto:${LEGAL_CONTROLLER_EMAIL}`} style={{ color: '#0066cc', textDecoration: 'none' }}>
                {LEGAL_CONTROLLER_EMAIL}
              </a>
            ) : (
              <Link href="/about#contact" style={{ color: '#0066cc', textDecoration: 'none' }}>
                contact form
              </Link>
            )}
            {LEGAL_CONTROLLER_ADDRESS && (
              <>
                <br />
                Address: {LEGAL_CONTROLLER_ADDRESS}
              </>
            )}
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Data we process</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            Depending on how you use Fundradar, we may process:
          </p>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Account data (name, email, hashed password, session identifiers).</li>
            <li>Subscription data (email, Stripe customer/subscription IDs, status).</li>
            <li>Watchlist data (saved watchlist names and selected funds).</li>
            <li>Contact-form data (name, email, message, anti-spam metadata, IP address).</li>
            <li>
              Technical and usage data (page events, browser/device data, cookie/local-storage
              identifiers, conversion events).
            </li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Purposes and legal bases</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>
              <strong>Provide the service</strong> (accounts, sessions, watchlists, subscription
              access): performance of a contract.
            </li>
            <li>
              <strong>Process billing and subscription lifecycle</strong>: performance of a contract
              and legal obligations.
            </li>
            <li>
              <strong>Send requested communications</strong> (including weekly signals digests for
              active subscribers): performance of a contract and legitimate interest.
            </li>
            <li>
              <strong>Security and anti-spam</strong> (rate limiting, reCAPTCHA, abuse prevention):
              legitimate interest.
            </li>
            <li>
              <strong>Analytics and conversion measurement</strong> (GTM/analytics/ad tags): consent
              where required by EU/Italian cookie rules.
            </li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Cookies, tags, and consent</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We use essential cookies for login/security and, only when consent is given, optional
            analytics and conversion tags. Our site uses Google Tag Manager, which may run Google
            Analytics and LinkedIn Insight Tag when enabled. We also use Vercel Analytics and send a
            purchase event after successful subscription checkout for conversion measurement. See our{' '}
            <Link href="/cookie-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Cookie Policy
            </Link>{' '}
            for details.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Recipients and processors</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            We do not sell personal data. Data may be processed by service providers acting on our
            behalf, including:
          </p>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Stripe (payments and subscription lifecycle events).</li>
            <li>Google (Tag Manager, Analytics, reCAPTCHA).</li>
            <li>LinkedIn (Insight Tag measurement, when enabled).</li>
            <li>Vercel (hosting and analytics infrastructure).</li>
            <li>Resend (contact-form email delivery).</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. International transfers</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Some providers may process data outside the EEA. Where applicable, transfers rely on
            GDPR-compliant safeguards (such as adequacy decisions or Standard Contractual Clauses)
            made available by the relevant providers.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>7. Retention</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Session cookie data: up to 7 days unless deleted sooner.</li>
            <li>Account and watchlist data: while the account remains active.</li>
            <li>Subscription records: as needed for billing, tax, and compliance obligations.</li>
            <li>Contact requests: for the time needed to handle the request and follow-up.</li>
            <li>Cookie-consent preference: up to 6 months unless changed earlier.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>8. Your rights</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Under GDPR, you may have rights of access, rectification, erasure, restriction,
            portability, and objection, plus the right to withdraw consent at any time for
            consent-based processing. You also have the right to lodge a complaint with the Italian
            supervisory authority (Garante per la protezione dei dati personali).
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>9. How to exercise rights</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            To submit a privacy request, contact us using the details above or our{' '}
            <Link href="/about#contact" style={{ color: '#0066cc', textDecoration: 'none' }}>
              contact form
            </Link>.
            We respond within applicable legal deadlines. You can find more information at{' '}
            <a
              href="https://www.garanteprivacy.it/"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#0066cc', textDecoration: 'none' }}
            >
              garanteprivacy.it
            </a>.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>10. Policy updates</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We may update this policy from time to time. Material changes will be reflected by
            updating the date at the top of this page.
          </p>
        </section>
      </div>
    </div>
  );
}
