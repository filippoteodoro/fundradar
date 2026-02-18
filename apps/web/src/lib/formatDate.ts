/**
 * Shared date formatting utility for Fundradar.
 * Normalizes Italian-format and other non-standard dates to YYYY-MM-DD.
 */

const ITALIAN_MONTHS: Record<string, string> = {
  gennaio: '01', febbraio: '02', marzo: '03', aprile: '04',
  maggio: '05', giugno: '06', luglio: '07', agosto: '08',
  settembre: '09', ottobre: '10', novembre: '11', dicembre: '12',
  // Abbreviated
  gen: '01', feb: '02', mar: '03', apr: '04',
  mag: '05', giu: '06', lug: '07', ago: '08',
  set: '09', ott: '10', nov: '11', dic: '12',
};

const ENGLISH_MONTHS: Record<string, string> = {
  january: '01', february: '02', march: '03', april: '04',
  may: '05', june: '06', july: '07', august: '08',
  september: '09', october: '10', november: '11', december: '12',
  jan: '01', feb: '02', mar: '03', apr: '04',
  jun: '06', jul: '07', aug: '08',
  sep: '09', oct: '10', nov: '11', dec: '12',
};

const ALL_MONTHS: Record<string, string> = { ...ITALIAN_MONTHS, ...ENGLISH_MONTHS };

/**
 * Normalize a date string to YYYY-MM-DD format.
 * Handles: Italian month names, location prefixes, DD/MM/YYYY, ISO strings.
 * Returns the raw string if nothing works.
 */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '';

  let s = dateStr.trim();

  // Already ISO YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

  // ISO datetime — take date part
  if (/^\d{4}-\d{2}-\d{2}T/.test(s)) return s.slice(0, 10);

  // Strip location prefix: "Padova, 16 Gen. 2026" → "16 Gen. 2026"
  s = s.replace(/^[A-Za-zÀ-ú]+,\s*/, '');

  // Strip trailing dots from abbreviated months: "Gen." → "Gen"
  s = s.replace(/\./g, '');

  // Pattern: "MonthName DD, YYYY" or "MonthName DD YYYY" (Italian/English)
  {
    const m = s.match(/^([A-Za-zÀ-ú]+)\s+(\d{1,2}),?\s+(\d{4})$/);
    if (m) {
      const month = ALL_MONTHS[m[1].toLowerCase()];
      if (month) return `${m[3]}-${month}-${m[2].padStart(2, '0')}`;
    }
  }

  // Pattern: "DD MonthName YYYY"
  {
    const m = s.match(/^(\d{1,2})\s+([A-Za-zÀ-ú]+)\s+(\d{4})$/);
    if (m) {
      const month = ALL_MONTHS[m[2].toLowerCase()];
      if (month) return `${m[3]}-${month}-${m[1].padStart(2, '0')}`;
    }
  }

  // Pattern: DD/MM/YYYY or D/M/YYYY
  {
    const m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  }

  // Pattern: DD-MM-YYYY
  {
    const m = s.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
    if (m) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  }

  // Last resort: try native Date parsing
  const parsed = new Date(s);
  if (!isNaN(parsed.getTime())) {
    return parsed.toISOString().split('T')[0];
  }

  // Nothing worked — return raw string
  return dateStr.trim();
}
