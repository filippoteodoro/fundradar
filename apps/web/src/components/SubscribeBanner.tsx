import Link from 'next/link';

export function SubscribeBanner() {
  return (
    <div style={{
      marginTop: '16px',
      padding: '20px 24px',
      background: 'linear-gradient(135deg, #1a1a2e 0%, #2d2d5e 100%)',
      borderRadius: '12px',
      textAlign: 'center',
    }}>
      <p style={{ color: 'white', fontSize: '15px', fontWeight: 600, margin: '0 0 4px 0' }}>
        Get the weekly Italian PE/VC digest
      </p>
      <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '13px', margin: '0 0 14px 0' }}>
        Never miss a deal, exit, fundraise, or key hire from funds active in Italy.
      </p>
      <Link href="/subscribe" style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '10px 22px',
        background: '#2563eb',
        color: 'white',
        borderRadius: '8px',
        fontSize: '14px',
        fontWeight: 600,
        textDecoration: 'none',
      }}>
        Get Signals
      </Link>
    </div>
  );
}
