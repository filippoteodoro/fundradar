'use client';

import React from 'react';

const DUAL_RANGE_CSS = `
.dual-range-thumb {
  -webkit-appearance: none;
  appearance: none;
  pointer-events: none;
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 24px;
  margin: 0;
  padding: 0;
  background: transparent;
}
.dual-range-thumb::-webkit-slider-runnable-track {
  height: 4px;
  background: transparent;
}
.dual-range-thumb::-webkit-slider-thumb {
  -webkit-appearance: none;
  pointer-events: auto;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #1565c0;
  border: 2px solid white;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
  margin-top: -7px;
}
.dual-range-thumb::-moz-range-track {
  height: 4px;
  background: transparent;
}
.dual-range-thumb::-moz-range-thumb {
  pointer-events: auto;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #1565c0;
  border: 2px solid white;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
`;

interface DualRangeSliderProps {
  min: number;
  max: number;
  step: number;
  valueMin: number;
  valueMax: number;
  onChange: (newMin: number, newMax: number) => void;
  formatLabel: (v: number) => string;
}

export function DualRangeSlider({
  min,
  max,
  step,
  valueMin,
  valueMax,
  onChange,
  formatLabel,
}: DualRangeSliderProps) {
  const range = max - min || 1;
  const pctMin = ((valueMin - min) / range) * 100;
  const pctMax = ((valueMax - min) / range) * 100;
  const minOnTop = valueMin >= valueMax;

  return (
    <div>
      <style dangerouslySetInnerHTML={{ __html: DUAL_RANGE_CSS }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
        <span style={{ fontSize: '13px', color: '#333', fontWeight: 500 }}>{formatLabel(valueMin)}</span>
        <span style={{ fontSize: '13px', color: '#333', fontWeight: 500 }}>{formatLabel(valueMax)}</span>
      </div>
      <div style={{ position: 'relative', height: '24px' }}>
        <div style={{
          position: 'absolute', top: '50%', transform: 'translateY(-50%)',
          left: 0, right: 0, height: '4px', borderRadius: '2px', background: '#e0e0e0',
        }} />
        <div style={{
          position: 'absolute', top: '50%', transform: 'translateY(-50%)',
          left: `${pctMin}%`, width: `${pctMax - pctMin}%`,
          height: '4px', borderRadius: '2px', background: '#1565c0',
        }} />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={valueMin}
          className="dual-range-thumb"
          style={{ zIndex: minOnTop ? 4 : 3 }}
          onChange={(e) => {
            const v = Number(e.target.value);
            onChange(Math.min(v, valueMax), valueMax);
          }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={valueMax}
          className="dual-range-thumb"
          style={{ zIndex: minOnTop ? 3 : 4 }}
          onChange={(e) => {
            const v = Number(e.target.value);
            onChange(valueMin, Math.max(v, valueMin));
          }}
        />
      </div>
    </div>
  );
}
