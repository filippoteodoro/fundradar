import { ImageResponse } from 'next/og';

export const runtime = 'edge';
export const alt = 'Fundradar';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: 'linear-gradient(135deg, #0f1c3d 0%, #1d4ed8 100%)',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          padding: '80px 72px',
          fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
        }}
      >
        <div
          style={{
            fontSize: 20,
            fontWeight: 600,
            color: 'rgba(255,255,255,0.9)',
            letterSpacing: 0.4,
            textTransform: 'uppercase',
          }}
        >
          Fundradar
        </div>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 20,
            maxWidth: 980,
          }}
        >
          <div
            style={{
              fontSize: 76,
              lineHeight: 1.05,
              fontWeight: 800,
              color: '#ffffff',
              letterSpacing: -1.6,
            }}
          >
            Browse PE/VC funds activity in Italy for free
          </div>
          <div
            style={{
              fontSize: 30,
              lineHeight: 1.2,
              fontWeight: 500,
              color: 'rgba(255,255,255,0.9)',
            }}
          >
            Source-cited signals and deals, updated daily.
          </div>
        </div>
        <div
          style={{
            fontSize: 24,
            fontWeight: 700,
            color: 'rgba(255,255,255,0.95)',
            opacity: 0.95,
          }}
        >
          fundradar.co
        </div>
      </div>
    ),
    size
  );
}
