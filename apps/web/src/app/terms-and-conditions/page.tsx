import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import { LEGAL_CONTROLLER_EMAIL, LEGAL_JURISDICTION } from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Terms and Conditions',
  description: 'Terms and conditions for using Fundradar.',
  alternates: { canonical: '/terms-and-conditions' },
};

const LAST_UPDATED = 'September 21, 2026';

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
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Scope</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            These terms govern your use of the Fundradar website. Fundradar is a free, open-source
            project. It has no user accounts and no paid features.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Informational nature of content</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Content is provided for informational purposes only. It does not constitute investment,
            legal, tax, accounting, or other professional advice, and should not be treated as a
            recommendation or solicitation to invest. See the{' '}
            <Link href="/disclaimer" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Disclaimer
            </Link>
            .
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Acceptable use</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Do not attempt unauthorized access to systems or data.</li>
            <li>Do not use automated methods that materially degrade service availability.</li>
            <li>Do not use the service for unlawful purposes or to violate third-party rights.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Source code and third-party marks</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            The Fundradar source code is released under the MIT License. Third-party names, logos,
            and marks remain the property of their respective owners.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Availability</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We may change, suspend, or discontinue the website or any feature at any time.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. Limitation of liability</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            To the maximum extent permitted by law, Fundradar is not liable for damages resulting
            from use of the website, service interruption, or reliance on website content. Nothing
            in these terms excludes liability where mandatory law prohibits exclusion.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>7. Governing law</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            These terms are governed by the laws of {LEGAL_JURISDICTION}. Mandatory consumer
            protection rules remain unaffected.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>8. Contact</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            For questions about these terms, contact: <TermsContact />.
          </p>
        </section>
      </div>
    </div>
  );
}
