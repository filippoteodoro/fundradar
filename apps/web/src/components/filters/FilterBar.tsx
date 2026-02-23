'use client';

import React, { type ReactNode } from 'react';

interface FilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  activeFilterCount: number;
  onClearAll: () => void;
  showFilters: boolean;
  onToggleFilters: () => void;
  filterPanel?: ReactNode;
  children?: ReactNode;
}

export function FilterBar({
  search,
  onSearchChange,
  searchPlaceholder = 'Search...',
  activeFilterCount,
  onClearAll,
  showFilters,
  onToggleFilters,
  filterPanel,
  children,
}: FilterBarProps) {
  return (
    <>
      <input
        type="text"
        placeholder={searchPlaceholder}
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        style={{
          width: '100%',
          padding: '12px 16px',
          fontSize: '16px',
          border: '1px solid #ddd',
          borderRadius: '8px',
          marginBottom: '16px',
          boxSizing: 'border-box',
        }}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <button
          onClick={onToggleFilters}
          style={{
            padding: '8px 16px',
            border: '1px solid #ddd',
            borderRadius: '8px',
            background: showFilters ? '#f0f0f0' : 'white',
            cursor: 'pointer',
            fontSize: '14px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span>{showFilters ? '\u25BC' : '\u25B6'}</span>
          Filters
          {activeFilterCount > 0 && (
            <span style={{
              background: '#1565c0',
              color: 'white',
              borderRadius: '50%',
              width: '20px',
              height: '20px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '12px',
            }}>
              {activeFilterCount}
            </span>
          )}
        </button>
        {activeFilterCount > 0 && (
          <button
            onClick={onClearAll}
            style={{
              padding: '8px 16px',
              border: 'none',
              background: 'none',
              color: '#1565c0',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            Clear all filters
          </button>
        )}
      </div>

      {showFilters && filterPanel}

      {children}
    </>
  );
}
