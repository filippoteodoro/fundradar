export default function NotFound() {
  return (
    <div style={{ textAlign: 'center', padding: '80px 24px' }}>
      <h1 style={{ fontSize: '48px', margin: '0 0 8px 0', color: '#1a1a2e' }}>404</h1>
      <p style={{ fontSize: '18px', color: '#666', margin: '0 0 24px 0' }}>
        This page could not be found.
      </p>
      <a
        href="/"
        style={{
          color: '#0066cc',
          textDecoration: 'none',
          fontSize: '16px',
        }}
      >
        &larr; Back to all funds
      </a>
    </div>
  );
}
