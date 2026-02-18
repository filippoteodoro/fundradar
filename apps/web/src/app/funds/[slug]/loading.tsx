export default function FundLoading() {
  const shimmer = {
    background: 'linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)',
    backgroundSize: '200% 100%',
    borderRadius: '8px',
  } as const;

  return (
    <div>
      <div style={{ ...shimmer, width: '120px', height: '14px', marginBottom: '16px' }} />
      <div
        style={{
          background: '#fff',
          border: '1px solid #eee',
          borderRadius: '12px',
          padding: '24px',
          marginBottom: '24px',
        }}
      >
        <div style={{ ...shimmer, width: '250px', height: '28px', marginBottom: '16px' }} />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '16px', marginBottom: '16px' }}>
          <div>
            <div style={{ ...shimmer, width: '60px', height: '12px', marginBottom: '6px' }} />
            <div style={{ ...shimmer, width: '140px', height: '16px' }} />
          </div>
          <div>
            <div style={{ ...shimmer, width: '60px', height: '12px', marginBottom: '6px' }} />
            <div style={{ ...shimmer, width: '280px', height: '16px' }} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <div style={{ ...shimmer, width: '100px', height: '28px', borderRadius: '4px' }} />
          <div style={{ ...shimmer, width: '80px', height: '28px', borderRadius: '4px' }} />
        </div>
        <div style={{ ...shimmer, width: '100%', height: '48px' }} />
      </div>
      <div style={{ ...shimmer, width: '160px', height: '24px', marginBottom: '16px' }} />
      <div
        style={{
          background: '#fff',
          border: '1px solid #eee',
          borderRadius: '12px',
          padding: '24px',
        }}
      >
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{ ...shimmer, width: '90%', height: '16px', marginBottom: '12px' }} />
        ))}
      </div>
    </div>
  );
}
