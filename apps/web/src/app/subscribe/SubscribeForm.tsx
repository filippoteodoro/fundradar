'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { LEGAL_BUNDLE_VERSION } from '@/lib/legal';

export function SubscribeForm() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [acceptedImmediateAccess, setAcceptedImmediateAccess] = useState(false);

  useEffect(() => {
    const handlePageShow = (e: PageTransitionEvent) => {
      if (e.persisted) setLoading(false);
    };
    window.addEventListener('pageshow', handlePageShow);
    return () => window.removeEventListener('pageshow', handlePageShow);
  }, []);

  async function handleClick() {
    if (!acceptedTerms) {
      setError('Please accept the Terms, Privacy Policy, and Cookie Policy to continue.');
      return;
    }
    if (!acceptedImmediateAccess) {
      setError('Please confirm immediate service activation to continue.');
      return;
    }

    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/stripe/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          acceptedLegal: acceptedTerms,
          acceptedLegalVersion: LEGAL_BUNDLE_VERSION,
          acceptedAt: new Date().toISOString(),
          acceptedFrom: 'subscribe_page',
          acceptedImmediateAccess,
          acceptedWithdrawalAcknowledgement: acceptedImmediateAccess,
        }),
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

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px' }}>
        <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '13px', color: '#444', lineHeight: 1.5 }}>
          <input
            type="checkbox"
            checked={acceptedTerms}
            onChange={(e) => setAcceptedTerms(e.target.checked)}
            style={{ marginTop: '2px' }}
          />
          <span>
            I have read and accept the{' '}
            <Link href="/terms-and-conditions" style={{ color: '#0066cc', textDecoration: 'underline' }}>
              Terms
            </Link>
            ,{' '}
            <Link href="/privacy-policy" style={{ color: '#0066cc', textDecoration: 'underline' }}>
              Privacy Policy
            </Link>
            , and{' '}
            <Link href="/cookie-policy" style={{ color: '#0066cc', textDecoration: 'underline' }}>
              Cookie Policy
            </Link>
            .
          </span>
        </label>
        <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '13px', color: '#444', lineHeight: 1.5 }}>
          <input
            type="checkbox"
            checked={acceptedImmediateAccess}
            onChange={(e) => setAcceptedImmediateAccess(e.target.checked)}
            style={{ marginTop: '2px' }}
          />
          <span>
            I request immediate activation of the subscription after payment and acknowledge this
            may affect statutory withdrawal rights as permitted by applicable consumer law.
          </span>
        </label>
      </div>

      <button
        onClick={handleClick}
        disabled={loading}
        style={{
          display: 'block',
          margin: '0 auto',
          padding: '12px 40px',
          background: loading ? '#ccc' : '#2563eb',
          color: 'white',
          border: 'none',
          borderRadius: '8px',
          fontSize: '16px',
          fontWeight: 600,
          cursor: loading ? 'not-allowed' : 'pointer',
        }}
      >
        {loading ? 'Redirecting to checkout...' : 'Subscribe'}
      </button>
    </div>
  );
}
