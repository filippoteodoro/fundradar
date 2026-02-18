'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { FundCategory } from '@fundradar/shared';
import { FUND_CATEGORY_LABELS } from '@fundradar/shared';
import type { MapFund, CityCluster } from './MapView';
import { CARD_RADIUS } from '@/lib/ui';

// Fix Leaflet default marker icon path issue with bundlers
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

function createColoredIcon(color: string): L.DivIcon {
  return L.divIcon({
    className: '',
    html: `<div style="
      width: 12px;
      height: 12px;
      background: ${color};
      border: 2px solid white;
      border-radius: 50%;
      box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    "></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    popupAnchor: [0, -10],
  });
}

interface LeafletMapProps {
  mapFunds: MapFund[];
  cityClusters: CityCluster[];
  categoryColors: Record<FundCategory, string>;
}

export function LeafletMap({ mapFunds, cityClusters, categoryColors }: LeafletMapProps) {
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    // Initialize the map
    const map = L.map(containerRef.current).setView([42.5, 12.5], 6);
    mapRef.current = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    // Individual fund markers
    for (const fund of mapFunds) {
      const marker = L.marker([fund.lat, fund.lng], {
        icon: createColoredIcon(categoryColors[fund.category] || '#666'),
      }).addTo(map);

      marker.bindTooltip(fund.name);
      marker.bindPopup(`
        <div style="min-width: 180px">
          <div style="font-weight: bold; margin-bottom: 4px">
            <a href="/funds/${fund.slug}" style="color: #1565c0; text-decoration: none">
              ${escapeHtml(fund.name)}
            </a>
          </div>
          <div style="
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
            background: ${categoryColors[fund.category] || '#666'};
            color: white;
          ">
            ${FUND_CATEGORY_LABELS[fund.category]}
          </div>
          ${fund.officeAddress
            ? `<div style="margin-top: 4px; font-size: 12px; color: #666">${escapeHtml(fund.officeAddress)}</div>`
            : fund.hq_city ? `<div style="margin-top: 4px; font-size: 12px; color: #666">${escapeHtml(fund.hq_city)}</div>` : ''}
        </div>
      `);
    }

    // City cluster markers
    for (const cluster of cityClusters) {
      const radius = Math.min(Math.max(cluster.funds.length * 2 + 8, 10), 40);
      const circle = L.circleMarker([cluster.lat, cluster.lng], {
        radius,
        fillColor: '#1a1a2e',
        fillOpacity: 0.6,
        color: 'white',
        weight: 2,
      }).addTo(map);

      circle.bindTooltip(`${cluster.city} (${cluster.funds.length} fund${cluster.funds.length !== 1 ? 's' : ''})`);

      const fundLinks = cluster.funds.slice(0, 20).map((fund) =>
        `<div style="margin-bottom: 4px">
          <a href="/funds/${fund.slug}" style="color: #1565c0; text-decoration: none; font-size: 13px">
            ${escapeHtml(fund.name)}
          </a>
          <span style="margin-left: 6px; font-size: 11px; color: ${categoryColors[fund.category] || '#666'}">
            ${FUND_CATEGORY_LABELS[fund.category]}
          </span>
          ${fund.address ? `<div style="font-size: 11px; color: #999">${escapeHtml(fund.address)}</div>` : ''}
        </div>`
      ).join('');

      const overflow = cluster.funds.length > 20
        ? `<div style="color: #999; font-size: 12px; margin-top: 4px">... and ${cluster.funds.length - 20} more</div>`
        : '';

      circle.bindPopup(`
        <div style="max-height: 300px; overflow-y: auto; min-width: 200px">
          <div style="font-weight: bold; margin-bottom: 8px; font-size: 14px">
            ${escapeHtml(cluster.city)} — ${cluster.funds.length} fund${cluster.funds.length !== 1 ? 's' : ''}
          </div>
          ${fundLinks}
          ${overflow}
        </div>
      `);
    }

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [mapFunds, cityClusters, categoryColors]);

  return (
    <div
      ref={containerRef}
      style={{
        height: '600px',
        width: '100%',
        borderRadius: CARD_RADIUS,
        overflow: 'hidden',
      }}
    />
  );
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
