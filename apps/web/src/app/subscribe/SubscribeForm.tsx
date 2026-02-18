'use client';

import { useState } from 'react';

export function SubscribeForm() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/stripe/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || 'Something went wrong');
        return;
      }

      if (data.url) {
        window.location.href = data.url;
      }
    } catch {
      setError('An error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      {error && (
        <div style={{
          background: '#fee',
          color: '#c00',
          padding: '12px',
          borderRadius: '8px',
          marginBottom: '16px',
          fontSize: '14px',
        }}>
          {error}
        </div>
      )}

      <button
        onClick={handleClick}
        disabled={loading}
        style={{
          width: '100%',
          padding: '14px 16px',
          background: loading ? '#ccc' : '#2563eb',
          color: 'white',
          border: 'none',
          borderRadius: '8px',
          fontSize: '16px',
          fontWeight: 600,
          cursor: loading ? 'not-allowed' : 'pointer',
          boxSizing: 'border-box',
        }}
      >
        {loading ? 'Redirecting to checkout...' : 'Subscribe'}
      </button>
    </div>
  );
}
