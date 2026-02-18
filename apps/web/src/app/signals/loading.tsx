export default function SignalsLoading() {
  const shimmer = {
    background: 'linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)',
    backgroundSize: '200% 100%',
    borderRadius: '8px',
  } as const;

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <div style={{ ...shimmer, width: '200px', height: '28px', marginBottom: '8px' }} />
        <div style={{ ...shimmer, width: '320px', height: '16px' }} />
      </div>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', flexWrap: 'wrap' }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} style={{ ...shimmer, width: '80px', height: '32px', borderRadius: '16px' }} />
        ))}
      </div>
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          style={{
            background: '#fff',
            border: '1px solid #eee',
            borderRadius: '12px',
            padding: '20px',
            marginBottom: '12px',
          }}
        >
          <div style={{ ...shimmer, width: '120px', height: '14px', marginBottom: '8px' }} />
          <div style={{ ...shimmer, width: '90%', height: '18px', marginBottom: '6px' }} />
          <div style={{ ...shimmer, width: '60%', height: '14px' }} />
        </div>
      ))}
    </div>
  );
}
