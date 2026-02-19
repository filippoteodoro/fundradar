'use client';

const CONSENT_KEY = 'fundradar_cookie_consent_v1';

export function CookiePreferenceReset() {
  function handleReset() {
    try {
      localStorage.removeItem(CONSENT_KEY);
    } catch {
      // Ignore storage failures
    }
    window.location.reload();
  }

  return (
    <button
      onClick={handleReset}
      style={{
        border: '1px solid #d1d5db',
        borderRadius: '8px',
        padding: '8px 12px',
        background: 'white',
        color: '#333',
        fontSize: '12px',
        cursor: 'pointer',
      }}
    >
      Re-open cookie choices
    </button>
  );
}
