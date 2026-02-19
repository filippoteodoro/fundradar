import type { Metadata } from 'next';
import Link from 'next/link';
import { CARD_PADDING, CARD_STYLE } from '@/lib/ui';
import {
  LEGAL_COMPANY_LEGAL_NAME,
  LEGAL_CONTROLLER_ADDRESS,
  LEGAL_CONTROLLER_EMAIL,
  LEGAL_CONTROLLER_NAME,
  LEGAL_PEC_EMAIL,
  LEGAL_REA_NUMBER,
  LEGAL_REGISTERED_CAPITAL,
  LEGAL_VAT_ID,
} from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Legal Notice',
  description: 'Provider and company information for Fundradar.',
  alternates: { canonical: '/legal-notice' },
};

const LAST_UPDATED = 'February 19, 2026';

function ValueOrFallback({ value, fallback }: { value: string; fallback: string }) {
  if (value && value.trim().length > 0) {
    return <>{value}</>;
  }
  return <span style={{ color: '#888' }}>{fallback}</span>;
}

export default function LegalNoticePage() {
  return (
    <div style={{ maxWidth: '760px', margin: '48px auto' }}>
      <div style={{ ...CARD_STYLE, padding: CARD_PADDING }}>
        <h1 style={{ margin: '0 0 8px 0', fontSize: '28px' }}>Legal Notice</h1>
        <p style={{ margin: '0 0 24px 0', color: '#666' }}>Last updated: {LAST_UPDATED}</p>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>1. Service provider</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>
              Trading name: <strong>{LEGAL_CONTROLLER_NAME}</strong>
            </li>
            <li>
              Legal name: <strong>{LEGAL_COMPANY_LEGAL_NAME}</strong>
            </li>
            <li>
              Registered office:{' '}
              <ValueOrFallback
                value={LEGAL_CONTROLLER_ADDRESS}
                fallback="Set NEXT_PUBLIC_LEGAL_CONTROLLER_ADDRESS"
              />
            </li>
            <li>
              VAT / P.IVA:{' '}
              <ValueOrFallback
                value={LEGAL_VAT_ID}
                fallback="Set NEXT_PUBLIC_LEGAL_VAT_ID"
              />
            </li>
            <li>
              REA / company register number:{' '}
              <ValueOrFallback
                value={LEGAL_REA_NUMBER}
                fallback="Set NEXT_PUBLIC_LEGAL_REA_NUMBER"
              />
            </li>
            <li>
              Share capital:{' '}
              <ValueOrFallback
                value={LEGAL_REGISTERED_CAPITAL}
                fallback="Set NEXT_PUBLIC_LEGAL_REGISTERED_CAPITAL"
              />
            </li>
          </ul>
        </section>

        <section style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>2. Contact channels</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', lineHeight: 1.8, color: '#444' }}>
            <li>
              Email:{' '}
              {LEGAL_CONTROLLER_EMAIL ? (
                <a href={`mailto:${LEGAL_CONTROLLER_EMAIL}`} style={{ color: '#0066cc', textDecoration: 'none' }}>
                  {LEGAL_CONTROLLER_EMAIL}
                </a>
              ) : (
                <span style={{ color: '#888' }}>Set NEXT_PUBLIC_LEGAL_CONTROLLER_EMAIL</span>
              )}
            </li>
            <li>
              PEC:{' '}
              {LEGAL_PEC_EMAIL ? (
                <a href={`mailto:${LEGAL_PEC_EMAIL}`} style={{ color: '#0066cc', textDecoration: 'none' }}>
                  {LEGAL_PEC_EMAIL}
                </a>
              ) : (
                <span style={{ color: '#888' }}>Set NEXT_PUBLIC_LEGAL_PEC_EMAIL</span>
              )}
            </li>
            <li>
              Web contact:{' '}
              <Link href="/about#contact" style={{ color: '#0066cc', textDecoration: 'none' }}>
                contact form
              </Link>
            </li>
          </ul>
        </section>

        <section>
          <h2 style={{ fontSize: '18px', margin: '0 0 8px 0' }}>3. Related policies</h2>
          <p style={{ margin: 0, lineHeight: 1.6, color: '#444' }}>
            See our{' '}
            <Link href="/terms-and-conditions" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Terms and Conditions
            </Link>
            ,{' '}
            <Link href="/privacy-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Privacy Policy
            </Link>
            ,{' '}
            <Link href="/cookie-policy" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Cookie Policy
            </Link>{' '}
            and{' '}
            <Link href="/disclaimer" style={{ color: '#0066cc', textDecoration: 'none' }}>
              Disclaimer
            </Link>
            .
          </p>
        </section>
      </div>
    </div>
  );
}
