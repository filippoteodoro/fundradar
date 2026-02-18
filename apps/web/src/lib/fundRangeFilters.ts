function formatScaledAum(value: number, suffix: 'T' | 'B' | 'M' | 'K'): string {
  // For >=10M/10B/10T, show no decimals and avoid rounding up (e.g. 10.5M -> 10M).
  const raw = (suffix !== 'K' && value >= 10)
    ? String(Math.floor(value))
    : (value % 1 === 0 ? value.toFixed(0) : value.toFixed(1));
  const normalized = raw.replace(/,(?=\d{3}\b)/g, '');
  return `€${normalized}${suffix}`;
}

export function formatAum(aum: number): string {
  if (aum >= 1e12) return formatScaledAum(aum / 1e12, 'T');
  if (aum >= 1e9) return formatScaledAum(aum / 1e9, 'B');
  if (aum >= 1e6) return formatScaledAum(aum / 1e6, 'M');
  if (aum >= 1e3) return formatScaledAum(aum / 1e3, 'K');
  return `€${aum}`;
}

export function buildAumStops(max: number): number[] {
  const stops = [0];
  const bases = [10, 25, 50, 100, 250, 500];
  for (const mult of [1e6, 1e9, 1e12]) {
    for (const base of bases) {
      const val = base * mult;
      if (val <= max) stops.push(val);
    }
  }
  if (stops[stops.length - 1] < max) stops.push(max);
  return stops;
}

export function buildInvestmentStops(max: number): number[] {
  if (max === 0) return [0];
  const stops = [0];
  const vals = [
    50e3, 100e3, 250e3, 500e3,
    1e6, 2.5e6, 5e6, 10e6, 25e6, 50e6, 100e6, 250e6, 500e6,
    1e9, 2.5e9, 5e9, 10e9,
  ];
  for (const val of vals) {
    if (val <= max) stops.push(val);
  }
  if (stops[stops.length - 1] < max) stops.push(max);
  return stops;
}

export function findNearestStopIndex(stops: number[], value: number): number {
  let closest = 0;
  let minDiff = Math.abs(stops[0] - value);
  for (let i = 1; i < stops.length; i++) {
    const diff = Math.abs(stops[i] - value);
    if (diff < minDiff) {
      closest = i;
      minDiff = diff;
    }
  }
  return closest;
}
