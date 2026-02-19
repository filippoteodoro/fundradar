import type { Metadata } from 'next';
import Script from 'next/script';
import Link from 'next/link';
import { BetaBadge } from '@/components/BetaBadge';
import { BetaBanner } from '@/components/BetaBanner';
import { HeaderNav } from '@/components/HeaderNav';
import { Analytics } from '@vercel/analytics/react';
import { getBaseUrl } from '@/lib/baseUrl';

const GTM_ID = 'GTM-P6LBQD4B';

export const metadata: Metadata = {
  metadataBase: new URL(getBaseUrl()),
  title: {
    default: 'Fundradar',
    template: '%s | Fundradar',
  },
  description: 'Free Italian funds directory built using publicly available data.',
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
      <head>
        <Script id="gtm" strategy="afterInteractive">
          {`(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','${GTM_ID}');`}
        </Script>
      </head>
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', background: '#fafafa' }}>
        <noscript>
          <iframe src={`https://www.googletagmanager.com/ns.html?id=${GTM_ID}`} height="0" width="0" style={{ display: 'none', visibility: 'hidden' }} />
        </noscript>
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
            .beta-badge { font-size: 11px !important; padding: 2px 8px 2px 5px !important; gap: 4px !important; }
            .beta-badge > span:first-child { width: 13px !important; height: 13px !important; font-size: 9px !important; }
            .header-cta { font-size: 13px !important; padding: 5px 10px !important; }
            @media (max-width: 380px) {
              .beta-badge { font-size: 10px !important; padding: 2px 7px 2px 4px !important; gap: 3px !important; }
              .beta-badge > span:first-child { width: 12px !important; height: 12px !important; font-size: 8px !important; }
              .header-cta { font-size: 11px !important; padding: 3px 6px !important; }
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
        <Analytics />
      </body>
    </html>
  );
}
