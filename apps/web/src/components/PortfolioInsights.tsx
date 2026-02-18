'use client';

import type { PortfolioCompany } from '@/lib/data';

interface PortfolioInsightsProps {
  companies: PortfolioCompany[];
  showStatus?: boolean;
  showSector?: boolean;
}

// Color palette for sectors
const SECTOR_COLORS = [
  '#1a1a2e', '#0f4c81', '#1565c0', '#1976d2', '#1e88e5',
  '#42a5f5', '#64b5f6', '#90caf9', '#bbdefb', '#e3f2fd',
];

export function PortfolioInsights({ companies, showStatus = true, showSector = true }: PortfolioInsightsProps) {
  if (companies.length === 0) return null;

  // Calculate status counts - only count companies with known status
  const currentCount = companies.filter(c => c.status === 'current').length;
  const exitedCount = companies.filter(c => c.status === 'exited').length;
  const partialCount = companies.filter(c => c.status === 'partial').length;
  const knownStatusCount = currentCount + exitedCount + partialCount;

  // Only show status chart if we have meaningful status data (at least some companies with known status)
  const hasStatusData = showStatus && knownStatusCount > 0;

  // Calculate sector distribution (sectors are already canonical from normalization)
  const sectorCounts: Record<string, number> = {};
  companies.forEach(c => {
    if (c.sector) {
      const sector = c.sector.trim();
      sectorCounts[sector] = (sectorCounts[sector] || 0) + 1;
    }
  });

  const sectorEntries = Object.entries(sectorCounts)
    .sort((a, b) => {
      const diff = b[1] - a[1];
      return diff !== 0 ? diff : a[0].localeCompare(b[0]);
    });

  const MAX_SECTOR_CARDS = 8;
  let visibleSectors = sectorEntries;
  if (sectorEntries.length > MAX_SECTOR_CARDS) {
    const keep = Math.max(1, MAX_SECTOR_CARDS - 1);
    const rest = sectorEntries.slice(keep);
    const otherCount = rest.reduce((sum, [, count]) => sum + count, 0);
    visibleSectors = [
      ...sectorEntries.slice(0, keep),
      ['Other', otherCount] as [string, number],
    ];
  }

  const hasSectorData = showSector && sectorEntries.length > 0;

  // Don't render anything if no useful data
  if (!hasStatusData && !hasSectorData) return null;

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: hasStatusData && hasSectorData ? 'minmax(200px, 300px) 1fr' : '1fr',
      gap: '32px',
      marginBottom: '24px',
    }}>
      {/* Investment Status - only show if we have status data */}
      {hasStatusData && <div style={{
        background: '#f8fafc',
        borderRadius: '12px',
        padding: '20px',
      }}>
        <h4 style={{ margin: '0 0 16px 0', fontSize: '14px', color: '#555', fontWeight: 600 }}>
          Investment Status
        </h4>

        {/* Status bars: current, partial, exited */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Current */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '14px', fontWeight: 500, color: '#1a1a2e' }}>Current</span>
              <span style={{ fontSize: '14px', fontWeight: 600, color: '#1a1a2e' }}>
                {currentCount}
              </span>
            </div>
            <div style={{ height: '8px', background: '#e0e0e0', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{
                width: `${(currentCount / knownStatusCount) * 100}%`,
                height: '100%',
                background: '#1565c0',
                borderRadius: '4px',
              }} />
            </div>
          </div>

          {/* Partial (if any) */}
          {partialCount > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '14px', fontWeight: 500, color: '#64b5f6' }}>Partial</span>
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#64b5f6' }}>
                  {partialCount}
                </span>
              </div>
              <div style={{ height: '8px', background: '#e0e0e0', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{
                  width: `${(partialCount / knownStatusCount) * 100}%`,
                  height: '100%',
                  background: '#90caf9',
                  borderRadius: '4px',
                }} />
              </div>
            </div>
          )}

          {/* Exited */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '14px', fontWeight: 500, color: '#1976d2' }}>Exited</span>
              <span style={{ fontSize: '14px', fontWeight: 600, color: '#1976d2' }}>
                {exitedCount}
              </span>
            </div>
            <div style={{ height: '8px', background: '#e0e0e0', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{
                width: `${(exitedCount / knownStatusCount) * 100}%`,
                height: '100%',
                background: '#1e88e5',
                borderRadius: '4px',
              }} />
            </div>
          </div>
        </div>
      </div>}

      {/* Sector Distribution */}
      {hasSectorData && (
        <div style={{
          background: '#f8fafc',
          borderRadius: '12px',
          padding: '20px',
        }}>
          <div style={{
            display: 'flex',
            gap: '16px',
            flexWrap: 'wrap',
          }}>
            {visibleSectors.map(([sector, count], index) => (
              <div key={sector} style={{
                textAlign: 'center',
                flex: '1 1 80px',
                minWidth: '60px',
              }}>
                <div style={{
                  fontSize: '24px',
                  fontWeight: 600,
                  color: sector === 'Other' ? '#757575' : SECTOR_COLORS[index % SECTOR_COLORS.length],
                }}>
                  {count}
                </div>
                <div style={{
                  marginTop: '4px',
                  fontSize: '13px',
                  color: '#666',
                  lineHeight: 1.3,
                }}>
                  {sector}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
