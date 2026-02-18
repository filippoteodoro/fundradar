/**
 * Watchlist utilities for Fundradar
 *
 * Sprint 4: JSON-based watchlist storage
 * Future: Can be upgraded to Supabase
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';
import crypto from 'crypto';

export interface Watchlist {
  id: string;
  user_id: string;
  name: string;
  fund_slugs: string[];
  created_at: string;
  updated_at: string;
}

export interface WatchlistStore {
  watchlists: Watchlist[];
}

const WATCHLIST_STORE_PATH = join(process.cwd(), '..', '..', 'data', 'watchlists.json');

function loadWatchlistStore(): WatchlistStore {
  if (!existsSync(WATCHLIST_STORE_PATH)) {
    return { watchlists: [] };
  }
  try {
    return JSON.parse(readFileSync(WATCHLIST_STORE_PATH, 'utf-8'));
  } catch {
    return { watchlists: [] };
  }
}

const IS_READONLY = process.env.VERCEL === '1';

function saveWatchlistStore(store: WatchlistStore): void {
  if (IS_READONLY) return;
  writeFileSync(WATCHLIST_STORE_PATH, JSON.stringify(store, null, 2));
}

function generateId(): string {
  return crypto.randomBytes(8).toString('hex');
}

export function getUserWatchlists(userId: string): Watchlist[] {
  const store = loadWatchlistStore();
  return store.watchlists.filter(w => w.user_id === userId);
}

export function getWatchlistById(watchlistId: string, userId: string): Watchlist | null {
  const store = loadWatchlistStore();
  return store.watchlists.find(w => w.id === watchlistId && w.user_id === userId) || null;
}

export function createWatchlist(userId: string, name: string, fundSlugs: string[] = []): Watchlist {
  const store = loadWatchlistStore();
  const now = new Date().toISOString();

  const watchlist: Watchlist = {
    id: generateId(),
    user_id: userId,
    name,
    fund_slugs: fundSlugs,
    created_at: now,
    updated_at: now,
  };

  store.watchlists.push(watchlist);
  saveWatchlistStore(store);

  return watchlist;
}

export function updateWatchlist(
  watchlistId: string,
  userId: string,
  updates: { name?: string; fund_slugs?: string[] }
): Watchlist | null {
  const store = loadWatchlistStore();
  const index = store.watchlists.findIndex(w => w.id === watchlistId && w.user_id === userId);

  if (index === -1) {
    return null;
  }

  const watchlist = store.watchlists[index];
  const updated: Watchlist = {
    ...watchlist,
    ...(updates.name !== undefined && { name: updates.name }),
    ...(updates.fund_slugs !== undefined && { fund_slugs: updates.fund_slugs }),
    updated_at: new Date().toISOString(),
  };

  store.watchlists[index] = updated;
  saveWatchlistStore(store);

  return updated;
}

export function deleteWatchlist(watchlistId: string, userId: string): boolean {
  const store = loadWatchlistStore();
  const initialLength = store.watchlists.length;
  store.watchlists = store.watchlists.filter(w => !(w.id === watchlistId && w.user_id === userId));

  if (store.watchlists.length < initialLength) {
    saveWatchlistStore(store);
    return true;
  }

  return false;
}

export function addFundToWatchlist(watchlistId: string, userId: string, fundSlug: string): Watchlist | null {
  const watchlist = getWatchlistById(watchlistId, userId);
  if (!watchlist) {
    return null;
  }

  if (watchlist.fund_slugs.includes(fundSlug)) {
    return watchlist; // Already in watchlist
  }

  return updateWatchlist(watchlistId, userId, {
    fund_slugs: [...watchlist.fund_slugs, fundSlug],
  });
}

export function removeFundFromWatchlist(watchlistId: string, userId: string, fundSlug: string): Watchlist | null {
  const watchlist = getWatchlistById(watchlistId, userId);
  if (!watchlist) {
    return null;
  }

  return updateWatchlist(watchlistId, userId, {
    fund_slugs: watchlist.fund_slugs.filter(s => s !== fundSlug),
  });
}

export function isFundInAnyWatchlist(userId: string, fundSlug: string): boolean {
  const watchlists = getUserWatchlists(userId);
  return watchlists.some(w => w.fund_slugs.includes(fundSlug));
}

export function getWatchlistsContainingFund(userId: string, fundSlug: string): Watchlist[] {
  const watchlists = getUserWatchlists(userId);
  return watchlists.filter(w => w.fund_slugs.includes(fundSlug));
}
