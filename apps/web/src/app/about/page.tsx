import type { Metadata } from 'next';
import ContactForm from './ContactForm';
import { CARD_STYLE, CARD_PADDING } from '@/lib/ui';

export const metadata: Metadata = {
  title: 'About',
  description: 'Fundradar is a public, source-cited directory of investment funds active in Italy.',
  alternates: { canonical: '/about' },
};

export default function AboutPage() {
  return (
    <div style={{ maxWidth: '600px', margin: '48px auto' }}>
      <h1 style={{ margin: '0 0 24px 0', fontSize: '24px' }}>About Fundradar</h1>

      <section style={{ ...CARD_STYLE, padding: CARD_PADDING, marginBottom: '24px' }}>
        <h2 style={{ fontSize: '18px', margin: '0 0 12px 0' }}>What is Fundradar?</h2>
        <p style={{ lineHeight: 1.6, color: '#444', marginBottom: '12px' }}>
          Fundradar is a free, public directory of funds active in Italy, combined with a signals
          engine that tracks publicly observable events. Unlike traditional databases, every piece
          of information is source-cited with links to original sources.
        </p>
        <p style={{ lineHeight: 1.6, color: '#444' }}>
          All fund data, portfolios, and signals are freely accessible — no account required.{' '}
          <a href="/subscribe" style={{ color: '#0066cc', textDecoration: 'none' }}>Subscribe</a> to receive weekly email digests of new signals directly in your inbox.
        </p>
      </section>

      <section style={{ ...CARD_STYLE, padding: CARD_PADDING, marginBottom: '24px' }}>
        <h2 style={{ fontSize: '18px', marginBottom: '12px' }}>Reliability Contract</h2>
        <p style={{ lineHeight: 1.6, color: '#444', marginBottom: '12px' }}>
          We follow a strict reliability contract:
        </p>
        <ul style={{ lineHeight: 1.8, color: '#444', paddingLeft: '24px' }}>
          <li>Every signal has a source URL and observation date</li>
          <li>We never claim completeness (e.g., &quot;all hires&quot;)</li>
          <li>We use language like &quot;publicly observed signals&quot;</li>
          <li>We do not infer private facts (IRR, TVPI, &quot;top quartile&quot;)</li>
          <li>Raw data and extracted fields are stored separately</li>
        </ul>
      </section>

      <section style={{ ...CARD_STYLE, padding: CARD_PADDING, marginBottom: '24px' }}>
        <h2 style={{ fontSize: '18px', marginBottom: '12px' }}>Data Sources</h2>
        <p style={{ lineHeight: 1.6, color: '#444', marginBottom: '12px' }}>
          Current data sources include:
        </p>
        <ul style={{ lineHeight: 1.8, color: '#444', paddingLeft: '24px' }}>
          <li>
            <strong>AIFI (Associazione Italiana del Private Equity, Venture Capital e Private Debt)</strong>
            {' '}- Primary source for fund directory and member data
          </li>
          <li>
            <strong>PEM (Private Equity Monitor)</strong>
            {' '}- Deal data from LIUC Business School
          </li>
          <li>
            <strong>Fund websites</strong> - Portfolio companies, team pages, news
          </li>
          <li>
            <strong>Press releases</strong> - Fundraising announcements, deal news
          </li>
          <li>
            <strong>Public profiles</strong> - People analytics (seniority, backgrounds, education)
          </li>
        </ul>
      </section>

      <section id="contact" style={{ ...CARD_STYLE, padding: CARD_PADDING, marginBottom: '24px' }}>
        <h2 style={{ fontSize: '18px', marginBottom: '12px' }}>Contact</h2>
        <p style={{ lineHeight: 1.6, color: '#444', marginBottom: '16px' }}>
          For questions, data corrections, or partnership inquiries, please use the form below.
          We also very much welcome feedback on how to improve the site — whether it&apos;s a missing fund,
          an incorrect fund detail, a broken page, or a feature idea, we&apos;d love to hear from you.
        </p>
        <ContactForm />
      </section>
    </div>
  );
}
