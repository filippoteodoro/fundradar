'use client';

import { useState, useEffect, useRef } from 'react';
import Script from 'next/script';

declare global {
  interface Window {
    grecaptcha?: {
      render: (container: HTMLElement, params: {
        sitekey: string;
        callback: (token: string) => void;
        'expired-callback'?: () => void;
        'error-callback'?: () => void;
      }) => number;
      reset: (widgetId?: number) => void;
    };
  }
}

export default function ContactForm() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [honeypot, setHoneypot] = useState(''); // Anti-spam: hidden field
  const [formStartTime, setFormStartTime] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [mounted, setMounted] = useState(false);
  const [recaptchaToken, setRecaptchaToken] = useState<string | null>(null);
  const recaptchaRef = useRef<HTMLDivElement>(null);
  const recaptchaWidgetId = useRef<number | null>(null);
  const recaptchaSiteKey = process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY || '';
  const recaptchaConfigured = Boolean(recaptchaSiteKey);

  // Mount guard to avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
    setFormStartTime(Date.now());
  }, []);

  useEffect(() => {
    if (!mounted || !recaptchaConfigured || !recaptchaRef.current) return;

    const tryRender = () => {
      if (!window.grecaptcha || recaptchaWidgetId.current !== null) return;
      recaptchaWidgetId.current = window.grecaptcha.render(recaptchaRef.current!, {
        sitekey: recaptchaSiteKey,
        callback: (token: string) => setRecaptchaToken(token),
        'expired-callback': () => setRecaptchaToken(null),
        'error-callback': () => setRecaptchaToken(null),
      });
    };

    const interval = setInterval(tryRender, 200);
    tryRender();
    return () => clearInterval(interval);
  }, [mounted, recaptchaConfigured, recaptchaSiteKey]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMessage('');

    // Client-side validation
    if (!name.trim() || !email.trim() || !message.trim()) {
      setErrorMessage('Please fill in all fields.');
      setIsSubmitting(false);
      return;
    }

    if (!recaptchaConfigured) {
      setErrorMessage('Anti-spam verification is not configured.');
      setIsSubmitting(false);
      return;
    }

    if (!recaptchaToken) {
      setErrorMessage('Please complete the anti-spam check.');
      setIsSubmitting(false);
      return;
    }

    // Check minimum time (anti-bot: must take at least 3 seconds)
    const timeSpent = Date.now() - formStartTime;
    if (timeSpent < 3000) {
      setErrorMessage('Please take your time filling out the form.');
      setIsSubmitting(false);
      return;
    }

    try {
      const response = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim(),
          message: message.trim(),
          honeypot, // Should be empty
          recaptchaToken,
          timeSpent,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to send message');
      }

      setSubmitStatus('success');
      setName('');
      setEmail('');
      setMessage('');
      setRecaptchaToken(null);
      if (window.grecaptcha && recaptchaWidgetId.current !== null) {
        window.grecaptcha.reset(recaptchaWidgetId.current);
      }
      setFormStartTime(Date.now());
    } catch (error) {
      setSubmitStatus('error');
      setErrorMessage(error instanceof Error ? error.message : 'Failed to send message');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Don't render anything until mounted to avoid hydration mismatch
  if (!mounted) {
    return (
      <div style={{ maxWidth: '500px', padding: '20px 0', color: '#666' }}>
        Loading form...
      </div>
    );
  }

  if (submitStatus === 'success') {
    return (
      <div
        style={{
          background: '#e8f5e9',
          border: '1px solid #4caf50',
          borderRadius: '8px',
          padding: '24px',
          textAlign: 'center',
        }}
      >
        <p style={{ color: '#2e7d32', fontSize: '16px', margin: 0 }}>
          Thank you for your message! We&apos;ll get back to you soon.
        </p>
        <button
          onClick={() => setSubmitStatus('idle')}
          style={{
            marginTop: '16px',
            background: 'none',
            border: 'none',
            color: '#0066cc',
            cursor: 'pointer',
            textDecoration: 'underline',
          }}
        >
          Send another message
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: '500px' }}>
      {recaptchaConfigured && (
        <Script src="https://www.google.com/recaptcha/api.js?render=explicit" strategy="afterInteractive" />
      )}
      {/* Honeypot field - hidden from users, bots will fill it */}
      <div style={{ position: 'absolute', left: '-9999px' }} aria-hidden="true">
        <label htmlFor="website">Website</label>
        <input
          type="text"
          id="website"
          name="website"
          value={honeypot}
          onChange={(e) => setHoneypot(e.target.value)}
          tabIndex={-1}
          autoComplete="off"
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label htmlFor="name" style={{ display: 'block', marginBottom: '4px', fontWeight: 500 }}>
          Name
        </label>
        <input
          type="text"
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          style={{
            width: '100%',
            padding: '10px 12px',
            border: '1px solid #ccc',
            borderRadius: '8px',
            fontSize: '14px',
            boxSizing: 'border-box',
          }}
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label htmlFor="email" style={{ display: 'block', marginBottom: '4px', fontWeight: 500 }}>
          Email
        </label>
        <input
          type="email"
          id="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          style={{
            width: '100%',
            padding: '10px 12px',
            border: '1px solid #ccc',
            borderRadius: '8px',
            fontSize: '14px',
            boxSizing: 'border-box',
          }}
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label htmlFor="message" style={{ display: 'block', marginBottom: '4px', fontWeight: 500 }}>
          Message
        </label>
        <textarea
          id="message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          required
          rows={5}
          style={{
            width: '100%',
            padding: '10px 12px',
            border: '1px solid #ccc',
            borderRadius: '8px',
            fontSize: '14px',
            resize: 'vertical',
            boxSizing: 'border-box',
          }}
        />
      </div>
      {recaptchaConfigured ? (
        <div style={{ marginBottom: '16px' }}>
          <div ref={recaptchaRef} />
        </div>
      ) : (
        <div style={{ marginBottom: '16px', color: '#c00', fontSize: '13px' }}>
          reCAPTCHA is not configured.
        </div>
      )}

      {errorMessage && (
        <div
          style={{
            background: '#ffebee',
            border: '1px solid #f44336',
            borderRadius: '8px',
            padding: '12px',
            marginBottom: '16px',
            color: '#c62828',
            fontSize: '14px',
          }}
        >
          {errorMessage}
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitting || !recaptchaConfigured || !recaptchaToken}
        style={{
          background: isSubmitting ? '#ccc' : '#0066cc',
          color: 'white',
          border: 'none',
          padding: '12px 24px',
          borderRadius: '8px',
          fontSize: '14px',
          cursor: isSubmitting ? 'not-allowed' : 'pointer',
          fontWeight: 500,
        }}
      >
        {isSubmitting ? 'Sending...' : 'Send Message'}
      </button>
    </form>
  );
}
