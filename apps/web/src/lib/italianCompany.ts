/**
 * Italian company detection utilities.
 * Shared by PortfolioSection (fund detail) and company pages.
 */

export const ITALIAN_CITIES = new Set([
  'agropoli', 'ancona', 'arezzo', 'asti', 'avellino', 'bari', 'bergamo', 'biella', 'bologna',
  'bolzano', 'brescia', 'brindisi', 'cagliari', 'caserta', 'catania', 'catanzaro', 'como',
  'conegliano', 'cremona', 'ferrara', 'florence', 'firenze', 'foggia', 'forli', 'genoa', 'genova',
  'jesi', 'lainate', 'lecce', 'livorno', 'lucca', 'luzzara', 'mantova', 'martina franca',
  'milan', 'milano', 'modena', 'montemesola', 'monza', 'naples', 'napoli', 'novara',
  'padova', 'padua', 'palermo', 'parma', 'pavia', 'perugia', 'pesaro', 'pescara',
  'piacenza', 'pisa', 'pordenone', 'prato', 'ravenna', 'reggio emilia', 'reggio nell emilia',
  'rimini', 'rome', 'roma', 'salerno', 'sassari', 'siena', 'syracuse', 'siracusa',
  'somma vesuviana', 'taranto', 'terni', 'torino', 'turin', 'trento', 'treviso', 'trieste',
  'udine', 'varese', 'venice', 'venezia', 'verona', 'vicenza', 'villorba',
]);

export function extractCountry(headquarters: string | null | undefined): string | null {
  if (!headquarters) return null;
  const hq = headquarters.trim();
  if (/^europe\b/i.test(hq)) return null;
  const parts = hq.split(',').map(s => s.trim());
  if (parts.length >= 2) {
    const raw = parts[parts.length - 1].replace(/\s*\(.*\)$/, '').trim();
    if (raw === 'United Kingdom') return 'UK';
    if (raw === 'United States') return 'USA';
    return raw;
  }
  if (/italy$/i.test(hq)) return 'Italy';
  // Bare Italian city name (no comma, no country suffix)
  if (ITALIAN_CITIES.has(hq.toLowerCase())) return 'Italy';
  const known = ['France', 'Spain', 'Switzerland', 'UK', 'United Kingdom', 'Germany', 'Netherlands', 'Belgium', 'Austria', 'Portugal', 'Luxembourg', 'Ireland', 'USA', 'United States'];
  for (const c of known) {
    if (hq.toLowerCase() === c.toLowerCase()) {
      if (c === 'United Kingdom') return 'UK';
      if (c === 'United States') return 'USA';
      return c;
    }
  }
  return null;
}

export function isItalianCompany(company: { headquarters?: string | null; data_source?: string; region?: string | null }): boolean {
  const country = extractCountry(company.headquarters);
  if (country === 'Italy') return true;
  if (country) return false;
  // No country detected from headquarters (bare city name not in ITALIAN_CITIES, or null HQ):
  // non-Italian companies consistently include their country in the HQ string,
  // so if no foreign country is detected, assume Italian.
  return true;
}
