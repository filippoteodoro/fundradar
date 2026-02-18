'use client';

import React from 'react';

export interface ChipItem {
  value: string;
  label: string;
  count: number;
  color?: { bg: string; text: string };
}

interface FilterChipsProps {
  items: ChipItem[];
  activeValue: string;
  onSelect: (value: string) => void;
  allLabel?: string;
  allCount: number;
  /** Values forced to end of the list regardless of count (e.g. "other") */
  pinToEnd?: string[];
  /** Optional row label shown before the chips (e.g. "Type", "Sector") */
  rowLabel?: string;
}

export function FilterChips({
  items,
  activeValue,
  onSelect,
  allLabel = 'All',
  allCount,
  pinToEnd = [],
  rowLabel,
}: FilterChipsProps) {
  const pinSet = new Set(pinToEnd);
  const sortedItems = [...items].sort((a, b) => {
    const aPinned = pinSet.has(a.value);
    const bPinned = pinSet.has(b.value);
    if (aPinned !== bPinned) return aPinned ? 1 : -1;
    return b.count - a.count;
  });

  return (
    <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', flexWrap: 'wrap', alignItems: 'center' }}>
      {rowLabel && (
        <span style={{ fontSize: '12px', fontWeight: 600, color: '#999', textTransform: 'uppercase', letterSpacing: '0.5px', marginRight: '2px', whiteSpace: 'nowrap' }}>
          {rowLabel}
        </span>
      )}
      <button
        onClick={() => onSelect('all')}
        style={{
          padding: '6px 14px',
          border: activeValue === 'all' ? '2px solid #1565c0' : '1px solid #ddd',
          borderRadius: '20px',
          background: activeValue === 'all' ? '#e3f2fd' : 'white',
          color: activeValue === 'all' ? '#1565c0' : '#666',
          cursor: 'pointer',
          fontSize: '14px',
          fontWeight: activeValue === 'all' ? 600 : 400,
        }}
      >
        {allLabel} ({allCount})
      </button>
      {sortedItems.map((item) => {
        const isActive = activeValue === item.value;
        const activeBorder = item.color ? item.color.text : '#1565c0';
        const activeBg = item.color ? item.color.bg : '#e3f2fd';
        const activeColor = item.color ? item.color.text : '#1565c0';
        return (
          <button
            key={item.value}
            onClick={() => onSelect(item.value)}
            style={{
              padding: '6px 14px',
              border: isActive ? `2px solid ${activeBorder}` : '1px solid #ddd',
              borderRadius: '20px',
              background: isActive ? activeBg : 'white',
              color: isActive ? activeColor : '#666',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: isActive ? 600 : 400,
            }}
          >
            {item.label} ({item.count})
          </button>
        );
      })}
    </div>
  );
}
