'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

type ConsentState = 'accepted' | 'rejected' | null;

const GTM_ID = process.env.NEXT_PUBLIC_GTM_ID ?? 'GTM-P6LBQD4B';
const CONSENT_KEY = 'fundradar_cookie_consent_v1';
const CONSENT_MAX_AGE_MS = 180 * 24 * 60 * 60 * 1000; // 6 months

type ConsentWindow = Window & {
  dataLayer?: unknown[];
};

function loadGtmIfNeeded() {
  if (document.querySelector(`script[data-fundradar-gtm="${GTM_ID}"]`)) return;

  const w = window as ConsentWindow;
  w.dataLayer = w.dataLayer || [];
  w.dataLayer.push({
    'gtm.start': Date.now(),
    event: 'gtm.js',
  });

  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtm.js?id=${GTM_ID}`;
  script.setAttribute('data-fundradar-gtm', GTM_ID);
  document.head.appendChild(script);
}

function readStoredConsent(): ConsentState {
  try {
    const raw = localStorage.getItem(CONSENT_KEY);
    if (!raw) return null;

    // Backward-compatibility for legacy plain-string format
    if (raw === 'accepted' || raw === 'rejected') return raw;

    const parsed = JSON.parse(raw) as { choice?: string; savedAt?: number };
    if (
      (parsed.choice === 'accepted' || parsed.choice === 'rejected') &&
      typeof parsed.savedAt === 'number' &&
      Date.now() - parsed.savedAt <= CONSENT_MAX_AGE_MS
    ) {
      return parsed.choice;
    }

    localStorage.removeItem(CONSENT_KEY);
    return null;
  } catch {
    return null;
  }
}

function persistConsent(consent: Exclude<ConsentState, null>) {
  try {
    localStorage.setItem(
      CONSENT_KEY,
      JSON.stringify({
        choice: consent,
        savedAt: Date.now(),
      }),
    );
  } catch {
    // Ignore storage failures; runtime consent still applies
  }
}

export function ConsentManager() {
  const [consent, setConsent] = useState<ConsentState>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = readStoredConsent();
    setConsent(stored);
    loadGtmIfNeeded();
    setReady(true);
  }, []);

  const showBanner = ready && consent === null;

  const bannerTitle = useMemo(() => 'Cookies', []);

  function handleChoice(next: Exclude<ConsentState, null>) {
    setConsent(next);
    persistConsent(next);
  }

  return (
    <>
      {showBanner && (
        <div style={{
          position: 'fixed',
          left: '16px',
          right: '16px',
          bottom: '16px',
          zIndex: 3000,
          background: 'white',
          border: '1px solid #e5e7eb',
          borderRadius: '12px',
          padding: '12px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
          width: 'auto',
          maxWidth: '360px',
          marginLeft: 'auto',
          boxSizing: 'border-box',
        }}>
          <p style={{ margin: '0 0 8px 0', fontSize: '12px', fontWeight: 700, color: '#333' }}>
            {bannerTitle}
          </p>
          <p style={{ margin: '0 0 10px 0', fontSize: '12px', color: '#555', lineHeight: 1.45, overflowWrap: 'anywhere' }}>
            We use essential cookies plus optional analytics and conversion tracking. See our{' '}
            <Link href="/cookie-policy" style={{ color: '#0066cc', textDecoration: 'underline' }}>
              Cookie Policy
            </Link>.
          </p>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              onClick={() => handleChoice('accepted')}
              style={{
                border: 'none',
                borderRadius: '8px',
                padding: '7px 10px',
                background: '#1a1a2e',
                color: 'white',
                fontSize: '12px',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Accept
            </button>
            <button
              onClick={() => handleChoice('rejected')}
              style={{
                border: '1px solid #d1d5db',
                borderRadius: '8px',
                padding: '7px 10px',
                background: 'white',
                color: '#333',
                fontSize: '12px',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Reject optional
            </button>
          </div>
        </div>
      )}
    </>
  );
}
