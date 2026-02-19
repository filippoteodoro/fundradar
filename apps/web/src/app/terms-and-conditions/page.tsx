import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import {
  LEGAL_BILLING_PORTAL_URL,
  LEGAL_BUNDLE_VERSION,
  LEGAL_COMPANY_LEGAL_NAME,
  LEGAL_CONTROLLER_EMAIL,
  LEGAL_CONTROLLER_NAME,
  LEGAL_JURISDICTION,
  LEGAL_VAT_ID,
} from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Terms and Conditions',
  description: 'Terms and conditions for using Fundradar.',
  alternates: { canonical: '/terms-and-conditions' },
};

const LAST_UPDATED = 'February 19, 2026';

function TermsContact() {
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

export default function TermsAndConditionsPage() {
  return (
    <div style={{ maxWidth: '780px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Terms and Conditions</h1>
        <p style={{ margin: '0 0 8px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Legal bundle version: {LEGAL_BUNDLE_VERSION}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Provider and scope</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            These terms govern access to and use of Fundradar website features, including public
            data pages, signals feed, account functions, and paid subscription services.
          </p>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Service name: {LEGAL_CONTROLLER_NAME}</li>
            <li>Provider: {LEGAL_COMPANY_LEGAL_NAME}</li>
            {LEGAL_VAT_ID ? <li>VAT / P.IVA: {LEGAL_VAT_ID}</li> : null}
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Informational nature of content</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Content is provided for informational purposes only. It does not constitute investment,
            legal, tax, accounting, or other professional advice, and should not be treated as a
            recommendation or solicitation to invest.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Accounts and credentials</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            If account features are available in your environment, you are responsible for the
            confidentiality of your credentials and activities under your account. We may suspend or
            restrict access in case of abuse, security risks, or suspected unauthorized use.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Subscription service and pricing</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            Paid plans are billed through Stripe at the price displayed at checkout. Subscriptions
            renew automatically unless canceled before the next billing cycle. Payment processing
            and subscription lifecycle events are managed by Stripe.
          </p>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Active subscribers may receive weekly email signals digests, subject to suppression and
            preference controls.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Pre-contract information for consumers</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            Before payment, users can review pricing, billing frequency, and legal policies
            available in the footer and on the subscribe page.
          </p>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Main characteristics: access to paid subscription features and weekly signals digest.</li>
            <li>Total price: shown at checkout, including applicable taxes where required.</li>
            <li>Duration: recurring until canceled.</li>
            <li>Cancellation: possible at any time for future billing periods.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. Cancellation and refunds</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            You can cancel your subscription at any time via Stripe customer billing portal:{' '}
            <a href={LEGAL_BILLING_PORTAL_URL} target="_blank" rel="noopener noreferrer" style={{ color: '#0066cc', textDecoration: 'none' }}>
              manage billing
            </a>
            .
          </p>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Cancellation stops future renewals. Unless required by applicable law, amounts already
            paid for the current period are not refunded. Mandatory consumer rights under Italian/EU
            law remain unaffected.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>7. Acceptable use</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Do not attempt unauthorized access to systems, data, or user accounts.</li>
            <li>Do not use automated methods that materially degrade service availability.</li>
            <li>Do not use the service for unlawful purposes or to violate third-party rights.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>8. Intellectual property</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Fundradar trademarks, design elements, and original content are protected by applicable
            intellectual property law. Third-party names, logos, and marks remain property of their
            respective owners.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>9. Third-party services used</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            Service delivery may involve external providers, including Stripe (billing), Vercel
            (hosting/infrastructure), Google Tag Manager and Google Analytics (measurement, when
            consented), LinkedIn Insight Tag (measurement, when consented), Google reCAPTCHA
            (anti-spam), and Resend (contact-form email delivery).
          </p>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Data handling details are described in the{' '}
            <Link href="/privacy-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Privacy Policy
            </Link>{' '}
            and{' '}
            <Link href="/cookie-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Cookie Policy
            </Link>
            .
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>10. Availability and modifications</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We may update, suspend, or discontinue features to improve security, reliability, or
            functionality. We will make reasonable efforts to limit service disruption.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>11. Limitation of liability</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            To the maximum extent permitted by law, Fundradar is not liable for indirect,
            incidental, consequential, or loss-of-profit damages resulting from service use, service
            interruption, or reliance on website content. Nothing in these terms excludes liability
            where exclusion is prohibited by mandatory law.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>12. Governing law and jurisdiction</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            These terms are governed by the laws of {LEGAL_JURISDICTION}. If you are a consumer,
            mandatory jurisdiction rules under applicable consumer law remain unaffected.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>13. Changes to terms</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We may update these terms from time to time. Material changes are reflected by updating
            the date and legal bundle version at the top of this page.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>14. Contact</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            For legal questions, contact: <TermsContact />.
          </p>
        </section>
      </div>
    </div>
  );
}
