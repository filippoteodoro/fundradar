import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import { LEGAL_JURISDICTION } from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Terms and Conditions',
  description: 'Terms and conditions for using Fundradar.',
  alternates: { canonical: '/terms-and-conditions' },
};

const LAST_UPDATED = 'February 19, 2026';

export default function TermsAndConditionsPage() {
  return (
    <div style={{ maxWidth: '760px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Terms and Conditions</h1>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Scope</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            These terms govern your use of Fundradar website features, including public data pages,
            account features, and subscription services.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Informational nature</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Content is provided for informational purposes only and does not constitute investment,
            legal, tax, accounting, or other professional advice.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Accounts and security</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            If you create an account, you are responsible for account credentials and activities
            under your account. We may suspend access in case of abuse or security risk.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Paid subscriptions</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Subscriptions are billed as shown at checkout and may renew automatically unless canceled.
            Payments and subscription lifecycle events are handled by Stripe. Active subscribers may
            receive weekly email signals digests.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Cancellation and refunds</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            You can cancel at any time to stop future renewals. Unless required by applicable law,
            fees already paid are non-refundable. Mandatory statutory consumer rights are not limited
            by this clause.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. Acceptable use</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            You agree not to misuse the site, interfere with service availability, attempt
            unauthorized access, or use automated methods in ways that degrade the service.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>7. Intellectual property</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Fundradar brand, design, and original content are protected by applicable intellectual
            property laws. Third-party names and marks remain property of their respective owners.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>8. Third-party tools</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            The service may use third-party tools and processors including Google Tag Manager,
            Google Analytics, LinkedIn Insight Tag, Stripe, Vercel, Google reCAPTCHA, and Resend.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>9. Limitation of liability</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            To the maximum extent permitted by law, Fundradar is not liable for indirect,
            incidental, or consequential damages arising from use of the service or reliance on
            website content.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>10. Governing law and venue</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            These terms are governed by the laws of {LEGAL_JURISDICTION}. If you are a consumer,
            mandatory jurisdiction rules under applicable law remain unaffected.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>11. Changes to terms</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We may update these terms from time to time. Continued use after updates means acceptance
            of the revised terms.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>12. Contact</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            For legal questions, contact us via our{' '}
            <Link href="/about#contact" style={{ color: '#0066cc', textDecoration: 'none' }}>
              contact form
            </Link>.
          </p>
        </section>
      </div>
    </div>
  );
}
