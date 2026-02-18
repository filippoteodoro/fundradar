'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';

const linkStyle = { color: '#ccc', textDecoration: 'none', fontSize: '14px' } as const;

const ctaStyle = {
  background: '#2563eb',
  color: 'white',
  fontSize: '13px',
  fontWeight: 600,
  padding: '6px 14px',
  borderRadius: '8px',
  textDecoration: 'none',
  whiteSpace: 'nowrap',
} as const;

export function HeaderNav() {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  return (
    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
      {/* Get Signals — always visible */}
      <Link href="/subscribe" style={ctaStyle}>Get Signals</Link>

      {/* Desktop nav links */}
      <nav className="header-nav-desktop" style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
        <Link href="/" style={linkStyle}>Funds</Link>
        <Link href="/signals" style={linkStyle}>Signals</Link>
        <Link href="/map" style={linkStyle}>Map</Link>
        <Link href="/about" style={linkStyle}>About</Link>
      </nav>

      {/* Hamburger wrapper — position anchor for dropdown */}
      <div ref={menuRef} style={{ position: 'relative' }}>
        <button
          className="hamburger"
          onClick={() => setOpen(!open)}
          style={{
            display: 'none',
            background: 'none',
            border: 'none',
            color: 'white',
            fontSize: '22px',
            cursor: 'pointer',
            padding: '4px 8px',
            lineHeight: 1,
            width: '38px',
            textAlign: 'center',
          }}
          aria-label="Menu"
        >
          {open ? '\u2715' : '\u2630'}
        </button>

        {/* Dropdown — mobile only, anchored to hamburger button */}
        {open && (
          <nav
            className="header-dropdown"
            style={{
              display: 'none',
              position: 'absolute',
              top: 'calc(100% + 12px)',
              right: 0,
              background: '#1a1a2e',
              borderRadius: '12px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
              overflow: 'hidden',
              padding: '16px 24px',
              flexDirection: 'column',
              gap: '16px',
              minWidth: '160px',
              zIndex: 100,
            }}
          >
            <Link href="/" style={{ ...linkStyle, fontSize: '15px', padding: '4px 0' }} onClick={() => setOpen(false)}>Funds</Link>
            <Link href="/signals" style={{ ...linkStyle, fontSize: '15px', padding: '4px 0' }} onClick={() => setOpen(false)}>Signals</Link>
            <Link href="/map" style={{ ...linkStyle, fontSize: '15px', padding: '4px 0' }} onClick={() => setOpen(false)}>Map</Link>
            <Link href="/about" style={{ ...linkStyle, fontSize: '15px', padding: '4px 0' }} onClick={() => setOpen(false)}>About</Link>
          </nav>
        )}
      </div>
    </div>
  );
}
