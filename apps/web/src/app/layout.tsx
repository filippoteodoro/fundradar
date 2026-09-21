import type { Metadata } from 'next';
import Link from 'next/link';
import { cookies } from 'next/headers';
import { SpeedInsights } from '@vercel/speed-insights/next';
import { Analytics } from '@vercel/analytics/next';
import { BetaBadge } from '@/components/BetaBadge';
import { BetaBanner } from '@/components/BetaBanner';
import { HeaderNav } from '@/components/HeaderNav';
import { ConsentManager } from '@/components/ConsentManager';
import { getBaseUrl } from '@/lib/baseUrl';

export const metadata: Metadata = {
  metadataBase: new URL(getBaseUrl()),
  title: {
    default: 'Fundradar',
    template: '%s | Fundradar',
  },
  description: 'Browse PE/VC funds activity in italy for free',
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

function getTodayKey() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = await cookies();
  const bannerCookie = cookieStore.get('fundradar_beta_banner_dismissed');
  const bannerDismissed = bannerCookie?.value === getTodayKey();

  return (
    <html lang="en">
      <head />
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', background: '#fafafa' }}>
        <style dangerouslySetInnerHTML={{ __html: `
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
            .header-inner { gap: 8px !important; }
            .beta-badge { font-size: 11px !important; padding: 2px 8px 2px 5px !important; gap: 4px !important; }
            .beta-badge > span:first-child { width: 13px !important; height: 13px !important; font-size: 9px !important; }
            @media (max-width: 380px) {
              .beta-badge { font-size: 10px !important; padding: 2px 7px 2px 4px !important; gap: 3px !important; }
              .beta-badge > span:first-child { width: 12px !important; height: 12px !important; font-size: 8px !important; }
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
        <BetaBanner initialDismissed={bannerDismissed} />
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
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '10px',
            flexWrap: 'wrap',
          }}>
            <span>All data verified through public sources and updated daily.</span>
            <Link href="/terms-and-conditions" style={{ color: '#666', textDecoration: 'underline' }}>
              Terms
            </Link>
            <Link href="/privacy-policy" style={{ color: '#666', textDecoration: 'underline' }}>
              Privacy
            </Link>
            <Link href="/cookie-policy" style={{ color: '#666', textDecoration: 'underline' }}>
              Cookies
            </Link>
            <Link href="/disclaimer" style={{ color: '#666', textDecoration: 'underline' }}>
              Disclaimer
            </Link>
          </div>
        </footer>
        <ConsentManager />
        <SpeedInsights />
        <Analytics />
      </body>
    </html>
  );
}
