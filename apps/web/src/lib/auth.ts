/**
 * Simple auth utilities for Fundradar
 *
 * Sprint 4: Cookie-based sessions with JSON storage
 * Future: Can be upgraded to Supabase Auth
 */

import { cookies } from 'next/headers';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';
import crypto from 'crypto';

export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
  subscription_status: 'free' | 'pro';
}

export interface Session {
  id: string;
  user_id: string;
  created_at: string;
  expires_at: string;
}

interface AuthStore {
  users: User[];
  sessions: Session[];
}

const AUTH_STORE_PATH = join(process.cwd(), '..', '..', 'data', 'auth.json');
const SESSION_COOKIE_NAME = 'fundradar_session';
const SESSION_DURATION_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function loadAuthStore(): AuthStore {
  if (!existsSync(AUTH_STORE_PATH)) {
    return { users: [], sessions: [] };
  }
  try {
    return JSON.parse(readFileSync(AUTH_STORE_PATH, 'utf-8'));
  } catch {
    return { users: [], sessions: [] };
  }
}

const IS_READONLY = process.env.VERCEL === '1';

function saveAuthStore(store: AuthStore): void {
  if (IS_READONLY) return;
  writeFileSync(AUTH_STORE_PATH, JSON.stringify(store, null, 2));
}

function generateId(): string {
  return crypto.randomBytes(16).toString('hex');
}

function hashPassword(password: string): string {
  return crypto.createHash('sha256').update(password).digest('hex');
}

export async function createUser(email: string, password: string, name: string): Promise<User | null> {
  const store = loadAuthStore();

  // Check if user already exists
  if (store.users.some(u => u.email.toLowerCase() === email.toLowerCase())) {
    return null;
  }

  const user: User = {
    id: generateId(),
    email: email.toLowerCase(),
    name,
    created_at: new Date().toISOString(),
    subscription_status: 'free',
  };

  // Store password hash separately (in real app, use bcrypt)
  const userWithPassword = {
    ...user,
    password_hash: hashPassword(password),
  };

  store.users.push(userWithPassword as User & { password_hash: string });
  saveAuthStore(store);

  return user;
}

export async function verifyCredentials(email: string, password: string): Promise<User | null> {
  const store = loadAuthStore();
  const user = store.users.find(u => u.email.toLowerCase() === email.toLowerCase()) as (User & { password_hash?: string }) | undefined;

  if (!user || !user.password_hash) {
    return null;
  }

  if (user.password_hash !== hashPassword(password)) {
    return null;
  }

  // Return user without password hash
  const { password_hash, ...safeUser } = user;
  return safeUser;
}

export async function createSession(userId: string): Promise<Session> {
  const store = loadAuthStore();

  const session: Session = {
    id: generateId(),
    user_id: userId,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + SESSION_DURATION_MS).toISOString(),
  };

  store.sessions.push(session);
  saveAuthStore(store);

  // Set cookie
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE_NAME, session.id, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    expires: new Date(session.expires_at),
    path: '/',
  });

  return session;
}

export async function getCurrentUser(): Promise<User | null> {
  const cookieStore = await cookies();
  const sessionId = cookieStore.get(SESSION_COOKIE_NAME)?.value;

  if (!sessionId) {
    return null;
  }

  const store = loadAuthStore();
  const session = store.sessions.find(s => s.id === sessionId);

  if (!session) {
    return null;
  }

  // Check if session expired
  if (new Date(session.expires_at) < new Date()) {
    // Remove expired session
    store.sessions = store.sessions.filter(s => s.id !== sessionId);
    saveAuthStore(store);
    return null;
  }

  const user = store.users.find(u => u.id === session.user_id) as (User & { password_hash?: string }) | undefined;
  if (!user) {
    return null;
  }

  // Return user without password hash
  const { password_hash, ...safeUser } = user;
  return safeUser;
}

export async function logout(): Promise<void> {
  const cookieStore = await cookies();
  const sessionId = cookieStore.get(SESSION_COOKIE_NAME)?.value;

  if (sessionId) {
    const store = loadAuthStore();
    store.sessions = store.sessions.filter(s => s.id !== sessionId);
    saveAuthStore(store);
  }

  cookieStore.delete(SESSION_COOKIE_NAME);
}

export async function getUserById(userId: string): Promise<User | null> {
  const store = loadAuthStore();
  const user = store.users.find(u => u.id === userId) as (User & { password_hash?: string }) | undefined;

  if (!user) {
    return null;
  }

  const { password_hash, ...safeUser } = user;
  return safeUser;
}
