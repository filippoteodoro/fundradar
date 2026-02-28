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
          background: '#1d4ed8',
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif',
        }}
      >
        <div
          style={{
            fontSize: 168,
            fontWeight: 700,
            lineHeight: 1,
            color: '#ffffff',
            letterSpacing: '-1px',
          }}
        >
          Fundradar
        </div>
      </div>
    ),
    size
  );
}
