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
          background: '#1a1a2e',
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            fontSize: 96,
            fontWeight: 700,
            color: '#ffffff',
          }}
        >
          Fundradar
        </div>
      </div>
    ),
    { ...size }
  );
}
