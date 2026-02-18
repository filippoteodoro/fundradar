/**
 * Shared repo root resolution for Fundradar web app.
 *
 * Used by data.ts and signals_unified.ts. In Next.js dev/build, cwd is apps/web,
 * so we try multiple candidate paths to find the data directory.
 */

import { existsSync } from 'fs';
import { join } from 'path';

let cached: string | null = null;

export function getRepoRoot(): string {
  if (cached) return cached;

  const candidates = [
    join(process.cwd(), '..', '..'),  // From apps/web
    join(process.cwd(), '..'),        // From apps
    process.cwd(),                     // From repo root
  ];

  for (const candidate of candidates) {
    if (existsSync(join(candidate, 'data'))) {
      cached = candidate;
      return candidate;
    }
  }

  // Fallback to two levels up (apps/web -> repo root)
  cached = join(process.cwd(), '..', '..');
  return cached;
}
