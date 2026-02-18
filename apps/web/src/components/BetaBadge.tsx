export function BetaBadge() {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        border: '1px solid rgba(255, 215, 0, 0.5)',
        padding: '2px 10px 2px 6px',
        borderRadius: '8px',
        fontSize: '12px',
        fontWeight: 600,
        color: '#ffd700',
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '14px',
        height: '14px',
        borderRadius: '50%',
        background: '#ffd700',
        color: '#1a1a2e',
        fontSize: '10px',
        fontWeight: 'bold',
        lineHeight: 1,
        flexShrink: 0,
      }}>!</span>
      Italy Beta
    </span>
  );
}
