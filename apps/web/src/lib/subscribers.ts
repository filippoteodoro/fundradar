/**
 * Subscriber data layer for Fundradar Pro
 *
 * JSON file storage following the same pattern as auth.ts
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';
import crypto from 'crypto';

export interface Subscriber {
  id: string;
  email: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  status: 'active' | 'cancelled' | 'past_due';
  subscribed_at: string;
  cancelled_at: string | null;
  user_id: string | null;
  legal_acceptance_version: string | null;
  legal_acceptance_at: string | null;
  legal_acceptance_source: string | null;
  legal_acceptance_session_id: string | null;
}

interface SubscriberStore {
  subscribers: Subscriber[];
}

const STORE_PATH = join(process.cwd(), '..', '..', 'data', 'subscribers.json');

function loadStore(): SubscriberStore {
  if (!existsSync(STORE_PATH)) {
    return { subscribers: [] };
  }
  try {
    return JSON.parse(readFileSync(STORE_PATH, 'utf-8'));
  } catch {
    return { subscribers: [] };
  }
}

const IS_READONLY = process.env.VERCEL === '1';

function saveStore(store: SubscriberStore): void {
  if (IS_READONLY) return;
  writeFileSync(STORE_PATH, JSON.stringify(store, null, 2));
}

function generateId(): string {
  return crypto.randomBytes(16).toString('hex');
}

export function getSubscriberByEmail(email: string): Subscriber | null {
  const store = loadStore();
  return store.subscribers.find(s => s.email.toLowerCase() === email.toLowerCase()) ?? null;
}

export function getSubscriberByStripeCustomerId(customerId: string): Subscriber | null {
  const store = loadStore();
  return store.subscribers.find(s => s.stripe_customer_id === customerId) ?? null;
}

export function createSubscriber(data: {
  email: string;
  stripe_customer_id: string;
  stripe_subscription_id: string;
  user_id?: string;
  legal_acceptance_version?: string;
  legal_acceptance_at?: string;
  legal_acceptance_source?: string;
  legal_acceptance_session_id?: string;
}): Subscriber {
  const store = loadStore();

  // If subscriber with this email already exists, update them
  const existing = store.subscribers.find(s => s.email.toLowerCase() === data.email.toLowerCase());
  if (existing) {
    existing.stripe_customer_id = data.stripe_customer_id;
    existing.stripe_subscription_id = data.stripe_subscription_id;
    existing.status = 'active';
    existing.subscribed_at = new Date().toISOString();
    existing.cancelled_at = null;
    if (data.user_id) existing.user_id = data.user_id;
    if (data.legal_acceptance_version) existing.legal_acceptance_version = data.legal_acceptance_version;
    if (data.legal_acceptance_at) existing.legal_acceptance_at = data.legal_acceptance_at;
    if (data.legal_acceptance_source) existing.legal_acceptance_source = data.legal_acceptance_source;
    if (data.legal_acceptance_session_id) existing.legal_acceptance_session_id = data.legal_acceptance_session_id;
    saveStore(store);
    return existing;
  }

  const subscriber: Subscriber = {
    id: generateId(),
    email: data.email.toLowerCase(),
    stripe_customer_id: data.stripe_customer_id,
    stripe_subscription_id: data.stripe_subscription_id,
    status: 'active',
    subscribed_at: new Date().toISOString(),
    cancelled_at: null,
    user_id: data.user_id ?? null,
    legal_acceptance_version: data.legal_acceptance_version ?? null,
    legal_acceptance_at: data.legal_acceptance_at ?? null,
    legal_acceptance_source: data.legal_acceptance_source ?? null,
    legal_acceptance_session_id: data.legal_acceptance_session_id ?? null,
  };

  store.subscribers.push(subscriber);
  saveStore(store);
  return subscriber;
}

export function updateSubscriberStatus(
  stripeSubscriptionId: string,
  status: 'active' | 'cancelled' | 'past_due',
): Subscriber | null {
  const store = loadStore();
  const subscriber = store.subscribers.find(s => s.stripe_subscription_id === stripeSubscriptionId);
  if (!subscriber) return null;

  subscriber.status = status;
  if (status === 'cancelled') {
    subscriber.cancelled_at = new Date().toISOString();
  }
  saveStore(store);
  return subscriber;
}

export function getAllActiveSubscribers(): Subscriber[] {
  const store = loadStore();
  return store.subscribers.filter(s => s.status === 'active');
}

export function isActiveSubscriber(email: string): boolean {
  const subscriber = getSubscriberByEmail(email);
  return subscriber?.status === 'active';
}
