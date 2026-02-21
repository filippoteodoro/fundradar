import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import {
  LEGAL_BUNDLE_VERSION,
  LEGAL_CONTROLLER_ADDRESS,
  LEGAL_CONTROLLER_EMAIL,
  LEGAL_CONTROLLER_NAME,
  LEGAL_DIGEST_UNSUBSCRIBE_EMAIL,
} from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Privacy policy for Fundradar.',
  alternates: { canonical: '/privacy-policy' },
};

const LAST_UPDATED = 'February 21, 2026';

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
        <p style={{ margin: '0 0 8px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Legal bundle version: {LEGAL_BUNDLE_VERSION}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Data controller</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            The controller is <strong>{LEGAL_CONTROLLER_NAME}</strong>.
            <br />
            Contact: <ControllerContact />
            {LEGAL_CONTROLLER_ADDRESS ? (
              <>
                <br />
                Address: {LEGAL_CONTROLLER_ADDRESS}
              </>
            ) : null}
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Data we process</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Account data: name, email, password hash, session identifiers.</li>
            <li>Subscription data: email, Stripe customer/subscription IDs, payment status events.</li>
            <li>Watchlist data: lists and selected funds.</li>
            <li>Contact-form data: name, email, message, anti-spam metadata, IP address.</li>
            <li>
              Technical and usage data: browser/device data, page events, local-storage or cookie
              identifiers, conversion events, and event metadata such as URL/path and purchase event
              parameters (for example value, currency, and transaction/session identifier).
            </li>
            <li>Operational audit data: policy version and timestamp acceptance for subscriptions.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Sources of data</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Directly from you (signup, checkout, forms, website interaction).</li>
            <li>From payment and infrastructure providers acting on our instructions.</li>
            <li>From automated anti-spam and security checks.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>4. Purposes and legal bases (GDPR)</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>
              Service provision (accounts, watchlists, subscription access): performance of a
              contract.
            </li>
            <li>
              Billing and subscription lifecycle management: performance of a contract and legal
              obligations.
            </li>
            <li>
              Weekly subscriber digest and essential service communications: performance of a
              contract and legitimate interest in service operation.
            </li>
            <li>
              Security, anti-spam, and abuse prevention (rate-limiting, reCAPTCHA): legitimate
              interest.
            </li>
            <li>
              Analytics and conversion measurement (Tag Manager / analytics / ad tags): consent
              where required by EU and Italian cookie rules.
            </li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>5. Cookies, tags, and consent</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            We use essential session/security cookies and optional analytics/conversion tags only
            after consent. Consent choices are stored for up to 6 months and can be reset from the{' '}
            <Link href="/cookie-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Cookie Policy
            </Link>{' '}
            page.
          </p>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Optional measurement stack can include Google Tag Manager, Google Analytics, LinkedIn
            Insight Tag, Meta Pixel (Facebook), and Vercel Analytics when consent is granted.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>6. Recipients and processors</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            We do not sell personal data. Data may be processed by service providers acting as
            processors or independent controllers as applicable:
          </p>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Stripe: payment processing and subscription lifecycle events.</li>
            <li>Vercel: hosting and infrastructure operations.</li>
            <li>Google: Tag Manager, Analytics, and reCAPTCHA services.</li>
            <li>LinkedIn: Insight Tag conversion/measurement events when consented.</li>
            <li>Meta Platforms: Meta Pixel conversion/measurement events when consented.</li>
            <li>Resend: contact-form email delivery.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>7. International transfers</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Some providers may process data outside the EEA. Where this occurs, transfers are based
            on GDPR-compliant safeguards such as adequacy decisions and/or Standard Contractual
            Clauses made available by providers.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>8. Retention periods</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>Session data: up to 7 days unless deleted earlier.</li>
            <li>Account and watchlist data: until account deletion request or service retirement.</li>
            <li>Subscription and legal accounting records: for statutory tax/accounting periods.</li>
            <li>Contact requests: up to 24 months from closure unless longer retention is required.</li>
            <li>Cookie consent preference: up to 6 months unless changed earlier.</li>
            <li>Subscription legal-acceptance evidence: while subscription records are retained.</li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>9. Your GDPR rights</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            Subject to legal conditions, you may request access, rectification, erasure,
            restriction, portability, objection, and withdrawal of consent for consent-based
            processing.
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

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>10. How to exercise rights</h2>
          <p style={{ margin: '0 0 8px 0', lineHeight: 1.6, color: '#444' }}>
            Send your request to <ControllerContact /> with enough information to verify identity.
            We may request additional verification data where needed to protect account security.
          </p>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We respond within the timelines required by law. Digest-only opt-out requests can also
            be sent to{' '}
            {LEGAL_DIGEST_UNSUBSCRIBE_EMAIL ? (
              <a href={`mailto:${LEGAL_DIGEST_UNSUBSCRIBE_EMAIL}`} style={{ color: '#0066cc', textDecoration: 'none' }}>
                {LEGAL_DIGEST_UNSUBSCRIBE_EMAIL}
              </a>
            ) : (
              <ControllerContact />
            )}
            .
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>11. Children</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            Fundradar is not directed to children under 18. If you believe personal data of a minor
            was submitted, contact us to request deletion.
          </p>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>12. Automated decision-making</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We do not perform decisions producing legal or similarly significant effects solely by
            automated means on users of this service.
          </p>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>13. Policy updates</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            We may update this policy from time to time. Material changes are reflected by the date
            and legal bundle version shown at the top of this page.
          </p>
        </section>
      </div>
    </div>
  );
}
