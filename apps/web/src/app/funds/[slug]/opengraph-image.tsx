import { ImageResponse } from 'next/og';
import { getAllFunds } from '@/lib/data';

export const alt = 'Fundradar';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export function generateStaticParams() {
  return getAllFunds().map((f) => ({ slug: f.slug }));
}

export default async function Image() {
  const interBold = await fetch(
    new URL('https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuFuYMZhrib2Bg-4.ttf')
  ).then((res) => res.arrayBuffer());

  return new ImageResponse(
    (
      <div
        style={{
          background: '#0d0f1c',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'Inter',
        }}
      >
        <div
          style={{
            fontSize: 180,
            fontWeight: 700,
            color: '#ffffff',
            lineHeight: 1,
          }}
        >
          F
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: 'Inter', data: interBold, weight: 700, style: 'normal' },
      ],
    }
  );
}
