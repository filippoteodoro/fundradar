'use client';

import React from 'react';

export interface DropdownOption {
  value: string;
  label: string;
}

interface FilterDropdownProps {
  label: string;
  value: string;
  options: DropdownOption[];
  allLabel?: string;
  onChange: (value: string) => void;
}

export function FilterDropdown({
  label,
  value,
  options,
  allLabel = 'All',
  onChange,
}: FilterDropdownProps) {
  return (
    <div>
      <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500, fontSize: '14px' }}>
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%',
          padding: '8px 12px',
          border: '1px solid #ddd',
          borderRadius: '8px',
          fontSize: '14px',
          background: 'white',
        }}
      >
        <option value="all">{allLabel}</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
