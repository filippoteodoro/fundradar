import type { FundCategory } from '@fundradar/shared';

type ColorPair = { bg: string; text: string };

/**
 * Semantic colors for fund categories — each visually distinct.
 */
export const CATEGORY_COLORS: Record<FundCategory, ColorPair> = {
  pe: { bg: '#e3f2fd', text: '#1565c0' },           // Blue — classic finance
  vc: { bg: '#e8f5e9', text: '#2e7d32' },           // Green — startup/growth
  growth: { bg: '#e0f2f1', text: '#00695c' },        // Teal-green — growth but distinct from VC
  infra: { bg: '#ffebee', text: '#b71c1c' },         // Red — heavy/physical assets
  debt: { bg: '#f3e5f5', text: '#7b1fa2' },          // Purple — finance variant
  real_estate: { bg: '#efebe9', text: '#4e342e' },   // Brown — earth/property
  holdings: { bg: '#fff3e0', text: '#e65100' },      // Orange — wealth/conglomerate
  fund_of_funds: { bg: '#ede7f6', text: '#4527a0' }, // Deep indigo — meta/layered
  multi_strategy: { bg: '#f5f5f5', text: '#212121' }, // Black — diversified
  sovereign: { bg: '#e3f2fd', text: '#0d47a1' },     // Navy — government/authority
  bank: { bg: '#eceff1', text: '#455a64' },          // Slate — institutional
  asset_manager: { bg: '#f1f8e9', text: '#558b2f' }, // Olive — wealth management
  unknown: { bg: '#f5f5f5', text: '#616161' },       // Gray
};

/**
 * Semantic colors for portfolio sectors (30-sector taxonomy).
 *
 * Grouping logic:
 * - Indigo/Blue: Technology, Software, Telecommunications (digital/tech)
 * - Teal: Healthcare, Biotech & Pharma (life sciences)
 * - Green: Renewable Energy, Agriculture, Environmental Services, Waste Management (nature/environment)
 * - Cyan: Water & Utilities (water)
 * - Orange/Amber: Energy, Food & Beverage, Hospitality & Tourism (traditional energy & food)
 * - Red/Coral: Retail, Consumer Goods (consumer spending)
 * - Pink/Magenta: Fashion & Luxury (luxury)
 * - Purple: Media & Entertainment, Education (culture/knowledge)
 * - Slate/Navy: Financial Services, Insurance, Professional Services (business services)
 * - Gray/Steel: Industrial Manufacturing, Automotive, Aerospace & Defense, Mining & Metals, Chemicals, Packaging (heavy industry)
 * - Brown: Real Estate, Construction (built environment)
 * - Dark teal: Transportation & Logistics (movement)
 */
export const SECTOR_COLORS: Record<string, ColorPair> = {
  // Indigo/Blue — digital, tech, telecom
  'Technology':             { bg: '#e8eaf6', text: '#283593' },
  'Software':               { bg: '#e8eaf6', text: '#1a237e' },
  'Telecommunications':     { bg: '#e1f5fe', text: '#0277bd' },

  // Teal — life sciences, health
  'Healthcare':             { bg: '#e0f2f1', text: '#00695c' },
  'Biotech & Pharma':       { bg: '#e0f2f1', text: '#004d40' },

  // Green — nature, environment, agriculture
  'Renewable Energy':       { bg: '#e8f5e9', text: '#2e7d32' },
  'Agriculture':            { bg: '#f1f8e9', text: '#33691e' },
  'Environmental Services': { bg: '#f1f8e9', text: '#558b2f' },
  'Waste Management':       { bg: '#f9fbe7', text: '#827717' },

  // Cyan — water
  'Water & Utilities':      { bg: '#e0f7fa', text: '#006064' },

  // Orange/Amber — traditional energy, food, hospitality
  'Energy':                 { bg: '#fff3e0', text: '#e65100' },
  'Food & Beverage':        { bg: '#fff3e0', text: '#bf360c' },
  'Hospitality & Tourism':  { bg: '#fff8e1', text: '#ff6f00' },

  // Red/Coral — consumer spending
  'Retail':                 { bg: '#ffebee', text: '#c62828' },
  'Consumer Goods':         { bg: '#ffebee', text: '#b71c1c' },

  // Pink — luxury, fashion
  'Fashion & Luxury':       { bg: '#fce4ec', text: '#880e4f' },

  // Purple — culture, knowledge
  'Media & Entertainment':  { bg: '#f3e5f5', text: '#6a1b9a' },
  'Education':              { bg: '#f3e5f5', text: '#4a148c' },

  // Slate/Navy — business services, finance
  'Financial Services':     { bg: '#e3f2fd', text: '#0d47a1' },
  'Insurance':              { bg: '#eceff1', text: '#37474f' },
  'Professional Services':  { bg: '#eceff1', text: '#455a64' },

  // Gray/Steel — heavy industry
  'Industrial Manufacturing': { bg: '#eceff1', text: '#263238' },
  'Automotive':             { bg: '#eceff1', text: '#37474f' },
  'Aerospace & Defense':    { bg: '#eceff1', text: '#1b5e20' },
  'Chemicals':              { bg: '#fff8e1', text: '#f57f17' },
  'Mining & Metals':        { bg: '#eceff1', text: '#424242' },
  'Packaging':              { bg: '#efebe9', text: '#795548' },

  // Brown — built environment
  'Real Estate':            { bg: '#efebe9', text: '#4e342e' },
  'Real Estate / Mixed-use': { bg: '#efebe9', text: '#4e342e' },
  'Construction':           { bg: '#efebe9', text: '#5d4037' },

  // Dark teal — movement, logistics
  'Transportation & Logistics': { bg: '#e0f2f1', text: '#004d40' },
};

const DEFAULT_SECTOR_COLOR: ColorPair = { bg: '#f5f5f5', text: '#616161' };

export function getSectorColor(sector: string): ColorPair {
  return SECTOR_COLORS[sector] || DEFAULT_SECTOR_COLOR;
}
