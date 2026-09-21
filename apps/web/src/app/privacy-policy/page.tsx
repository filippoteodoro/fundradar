import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import { LEGAL_CONTROLLER_EMAIL, LEGAL_CONTROLLER_NAME } from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Privacy policy for Fundradar.',
  alternates: { canonical: '/privacy-policy' },
};

const LAST_UPDATED = 'September 21, 2026';

function ControllerContact() {
  if (LEGAL_CONTROLLER_EMAIL) {
    return (
      <a href={`mailto:${LEGAL_CONTROLLER_EMAIL}`} style={{ color: '#0066cc', textDecoration: 'none' }}>
        {LEGAL_CONTROLLER_EMAIL}
      </a>
    );
  }

  return (
    <Link href="/about#contact" style={{ color: '#0066cc', textDecoration: 'none' }}>
      contact form
    </Link>
  );
}

export default function PrivacyPolicyPage() {
  return (
    <div style={{ maxWidth: '780px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Privacy Policy</h1>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Data controller</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            The controller is <strong>{LEGAL_CONTROLLER_NAME}</strong>. Contact: <ControllerContact />
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Data we process</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            Fundradar is free. It has no user accounts, no subscriptions, and no payments. We
            process only:
          </p>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Contact-form data: name, email, message, IP address, and anti-spam metadata.</li>
            <li>
              Analytics data, only if you accept optional cookies: page views and browser/device data
              collected by Google Analytics through Google Tag Manager.
            </li>
            <li>
              Aggregate, cookieless usage and performance data collected by Vercel Analytics and
              Vercel Speed Insights.
            </li>
            <li>Server request logs kept by our hosting provider.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Purposes and legal bases (GDPR)</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Reply to contact-form messages: legitimate interest.</li>
            <li>Security, anti-spam, and abuse prevention (rate limits, reCAPTCHA): legitimate interest.</li>
            <li>Google Analytics: consent.</li>
            <li>Cookieless aggregate analytics and hosting logs: legitimate interest.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Processors</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            We do not sell personal data. These providers process data on our behalf:
          </p>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Vercel: hosting, Vercel Analytics, and Speed Insights.</li>
            <li>Google: Tag Manager, Analytics, and reCAPTCHA.</li>
            <li>Resend: contact-form email delivery.</li>
          </ul>
          <p style={{ margin: '8px 0 0 0', lineHeight: 1.6, color: '#444' }}>
            Some providers may process data outside the EEA under GDPR safeguards such as adequacy
            decisions or Standard Contractual Clauses.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Retention</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Contact messages: up to 24 months from the last reply.</li>
            <li>Cookie consent choice: up to 6 months, stored in your browser.</li>
            <li>Analytics data: as set by the analytics provider.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. Cookies</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            See the{' '}
            <Link href="/cookie-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Cookie Policy
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>7. Your rights</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            You may request access, rectification, erasure, restriction, portability, and objection,
            and you may withdraw consent at any time. Send your request to <ControllerContact />.
          </p>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            You can also lodge a complaint with the Italian supervisory authority (Garante per la
            protezione dei dati personali):{' '}
            <a
              href="https://www.garanteprivacy.it/"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#0066cc', textDecoration: 'none' }}
            >
              garanteprivacy.it
            </a>
            .
          </p>
        </section>
      </div>
    </div>
  );
}
