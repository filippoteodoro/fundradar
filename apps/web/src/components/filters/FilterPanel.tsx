'use client';

import React, { type ReactNode } from 'react';

interface FilterPanelProps {
  children: ReactNode;
}

export function FilterPanel({ children }: FilterPanelProps) {
  return (
    <div style={{
      background: '#f9f9f9',
      padding: '16px',
      borderRadius: '8px',
      marginBottom: '16px',
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
      gap: '16px',
    }}>
      {children}
    </div>
  );
}
