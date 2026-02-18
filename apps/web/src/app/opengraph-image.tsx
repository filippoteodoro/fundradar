import { ImageResponse } from 'next/og';

export const runtime = 'edge';
export const alt = 'Fundradar — PE & VC Fund Directory for Italy';
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
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            fontSize: 72,
            fontWeight: 700,
            color: '#ffffff',
            marginBottom: 16,
          }}
        >
          Fundradar
        </div>
        <div
          style={{
            fontSize: 32,
            color: '#94a3b8',
          }}
        >
          PE & VC Fund Directory for Italy
        </div>
      </div>
    ),
    { ...size }
  );
}
