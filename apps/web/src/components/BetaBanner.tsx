'use client';

import { useState, useEffect } from 'react';

const STORAGE_KEY = 'fundradar_beta_banner_dismissed';

function getTodayKey() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function BetaBanner() {
  const [dismissed, setDismissed] = useState(true); // hidden by default to avoid flash

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      setDismissed(stored === getTodayKey());
    } catch {
      // localStorage unavailable — keep hidden
    }
  }, []);

  if (dismissed) return null;

  const handleDismiss = () => {
    setDismissed(true);
    try {
      localStorage.setItem(STORAGE_KEY, getTodayKey());
    } catch {
      // ignore
    }
  };

  return (
    <div style={{
      background: '#fff3cd',
      borderBottom: '1px solid rgba(255, 215, 0, 0.55)',
      padding: '8px 24px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '8px',
    }}>
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '16px',
        height: '16px',
        borderRadius: '50%',
        background: '#ffd700',
        color: '#1a1a2e',
        fontSize: '11px',
        fontWeight: 'bold',
        lineHeight: 1,
        flexShrink: 0,
      }}>!</span>
      <span style={{ fontSize: '13px', fontWeight: 600, color: '#1a1a2e', lineHeight: 1.4 }}>
        Curated data is available only for Italy. We will expand based on subscribers&apos; requests
      </span>
      <button
        onClick={handleDismiss}
        aria-label="Dismiss"
        style={{
          background: 'none',
          border: 'none',
          color: '#1a1a2e',
          fontSize: '18px',
          cursor: 'pointer',
          padding: '0 4px',
          lineHeight: 1,
          flexShrink: 0,
          marginLeft: '8px',
        }}
      >
        {'\u00d7'}
      </button>
    </div>
  );
}
