/**
 * Fallback city coordinates for funds without geocoded addresses.
 * Used when a fund has hq_city but no hq_lat/hq_lng.
 */

interface CityCoord {
  lat: number;
  lng: number;
}

const CITY_COORDINATES: Record<string, CityCoord> = {
  // Major Italian cities
  'milano': { lat: 45.4642, lng: 9.1900 },
  'milan': { lat: 45.4642, lng: 9.1900 },
  'roma': { lat: 41.9028, lng: 12.4964 },
  'rome': { lat: 41.9028, lng: 12.4964 },
  'torino': { lat: 45.0703, lng: 7.6869 },
  'turin': { lat: 45.0703, lng: 7.6869 },
  'bologna': { lat: 44.4949, lng: 11.3426 },
  'firenze': { lat: 43.7696, lng: 11.2558 },
  'florence': { lat: 43.7696, lng: 11.2558 },
  'napoli': { lat: 40.8518, lng: 14.2681 },
  'naples': { lat: 40.8518, lng: 14.2681 },
  'venezia': { lat: 45.4408, lng: 12.3155 },
  'venice': { lat: 45.4408, lng: 12.3155 },
  'genova': { lat: 44.4056, lng: 8.9463 },
  'genoa': { lat: 44.4056, lng: 8.9463 },
  'padova': { lat: 45.4064, lng: 11.8768 },
  'padua': { lat: 45.4064, lng: 11.8768 },
  'verona': { lat: 45.4384, lng: 10.9917 },
  'brescia': { lat: 45.5416, lng: 10.2118 },
  'bergamo': { lat: 45.6983, lng: 9.6773 },
  'treviso': { lat: 45.6669, lng: 12.2430 },
  'vicenza': { lat: 45.5455, lng: 11.5354 },
  'trieste': { lat: 45.6495, lng: 13.7768 },
  'udine': { lat: 46.0711, lng: 13.2346 },
  'modena': { lat: 44.6471, lng: 10.9252 },
  'parma': { lat: 44.8015, lng: 10.3279 },
  'reggio emilia': { lat: 44.6989, lng: 10.6310 },
  'reggio nell\'emilia': { lat: 44.6989, lng: 10.6310 },
  'trento': { lat: 46.0748, lng: 11.1217 },
  'bolzano': { lat: 46.4983, lng: 11.3548 },
  'perugia': { lat: 43.1107, lng: 12.3908 },
  'bari': { lat: 41.1171, lng: 16.8719 },
  'catania': { lat: 37.5079, lng: 15.0830 },
  'palermo': { lat: 38.1157, lng: 13.3615 },
  'cagliari': { lat: 39.2238, lng: 9.1217 },
  'ancona': { lat: 43.6158, lng: 13.5189 },
  'lecce': { lat: 40.3516, lng: 18.1750 },
  'varese': { lat: 45.8206, lng: 8.8257 },
  'como': { lat: 45.8080, lng: 9.0852 },
  'monza': { lat: 45.5845, lng: 9.2744 },
  'pisa': { lat: 43.7228, lng: 10.4017 },
  'siena': { lat: 43.3188, lng: 11.3308 },
  'lucca': { lat: 43.8430, lng: 10.5027 },
  'rimini': { lat: 44.0678, lng: 12.5695 },
  'ravenna': { lat: 44.4184, lng: 12.2035 },
  'pesaro': { lat: 43.9096, lng: 12.9135 },
  'aosta': { lat: 45.7372, lng: 7.3150 },
  // European cities (for non-Italian funds in the DB)
  'london': { lat: 51.5074, lng: -0.1278 },
  'londra': { lat: 51.5074, lng: -0.1278 },
  'paris': { lat: 48.8566, lng: 2.3522 },
  'parigi': { lat: 48.8566, lng: 2.3522 },
  'luxembourg': { lat: 49.6117, lng: 6.1319 },
  'lussemburgo': { lat: 49.6117, lng: 6.1319 },
  'zurich': { lat: 47.3769, lng: 8.5417 },
  'zurigo': { lat: 47.3769, lng: 8.5417 },
  'amsterdam': { lat: 52.3676, lng: 4.9041 },
  'munich': { lat: 48.1351, lng: 11.5820 },
  'monaco di baviera': { lat: 48.1351, lng: 11.5820 },
  'frankfurt': { lat: 50.1109, lng: 8.6821 },
  'francoforte': { lat: 50.1109, lng: 8.6821 },
  'madrid': { lat: 40.4168, lng: -3.7038 },
  'barcelona': { lat: 41.3874, lng: 2.1686 },
  'barcellona': { lat: 41.3874, lng: 2.1686 },
  'brussels': { lat: 50.8503, lng: 4.3517 },
  'bruxelles': { lat: 50.8503, lng: 4.3517 },
};

/**
 * Look up coordinates for a city name.
 * Handles common normalizations (Milano/Milan, Roma/Rome, etc.)
 */
export function getCityCoordinates(city: string): CityCoord | null {
  const normalized = city.toLowerCase().trim();
  return CITY_COORDINATES[normalized] ?? null;
}
