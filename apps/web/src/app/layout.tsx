import type { Metadata } from 'next';
import Link from 'next/link';
import { BetaBadge } from '@/components/BetaBadge';
import { BetaBanner } from '@/components/BetaBanner';
import { HeaderNav } from '@/components/HeaderNav';
import { getBaseUrl } from '@/lib/baseUrl';

export const metadata: Metadata = {
  metadataBase: new URL(getBaseUrl()),
  title: {
    default: 'Fundradar',
    template: '%s | Fundradar',
  },
  description: 'Public directory of private equity and venture capital funds in Italy with source-cited signals, portfolio tracking, and deal history.',
  openGraph: {
    type: 'website',
    siteName: 'Fundradar',
    locale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', background: '#fafafa' }}>
        <style dangerouslySetInnerHTML={{ __html: `
          .mobile-show { display: none; }
          @media (max-width: 768px) {
            .hamburger {
              display: block !important;
            }
            .header-nav-desktop {
              display: none !important;
            }
            .header-dropdown {
              display: flex !important;
            }
            .fund-detail-grid {
              grid-template-columns: 1fr !important;
            }
            main {
              padding: 16px !important;
            }
            .mobile-hide { display: none !important; }
            .mobile-show { display: inline !important; }
            .header-inner { gap: 8px !important; }
            .beta-badge {
              font-size: 9px !important;
              padding: 2px 5px 2px 3px !important;
              gap: 2px !important;
              align-items: flex-start !important;
              line-height: 1.2 !important;
            }
            .beta-badge > span:first-child {
              width: 12px !important;
              height: 12px !important;
              font-size: 8px !important;
              margin-top: 1px !important;
            }
            .beta-text {
              display: inline-block !important;
              max-width: 28px !important;
            }
            .header-cta {
              font-size: 12px !important;
              padding: 4px 8px !important;
            }
          }
        `}} />
        <div style={{ position: 'sticky', top: 0, zIndex: 1000 }}>
        <header style={{
          background: '#1a1a2e',
          color: 'white',
          padding: '12px 24px',
        }}>
        <div className="header-inner" style={{
          maxWidth: '1200px',
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
        }}>
          <Link href="/" style={{ color: 'white', textDecoration: 'none', fontWeight: 'bold', fontSize: '18px' }}>
            Fundradar
          </Link>
          <BetaBadge />
          <HeaderNav />
        </div>
        </header>
        <BetaBanner />
        </div>
        <main style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
          {children}
        </main>
        <footer style={{
          textAlign: 'center',
          padding: '24px',
          color: '#666',
          fontSize: '14px',
          borderTop: '1px solid #eee',
          marginTop: '48px'
        }}>
          <p>All data verified through public sources. Data is updated daily.</p>
        </footer>
      </body>
    </html>
  );
}
