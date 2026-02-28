import { NextResponse } from 'next/server';
import Stripe from 'stripe';
import { getCurrentUser } from '@/lib/auth';
import { LEGAL_BUNDLE_VERSION } from '@/lib/legal';
import { getBaseUrl } from '@/lib/baseUrl';

function getStripe() {
  return new Stripe(process.env.STRIPE_SECRET_KEY!, {
    apiVersion: '2026-01-28.clover',
  });
}

export async function POST(request: Request) {
  try {
    if (!process.env.STRIPE_SECRET_KEY) {
      return NextResponse.json({ error: 'Payment not configured' }, { status: 500 });
    }
    const stripe = getStripe();

    if (!process.env.STRIPE_PRICE_ID) {
      console.error('STRIPE_PRICE_ID not configured');
      return NextResponse.json({ error: 'Payment not configured' }, { status: 500 });
    }

    const body = await request.json().catch(() => ({}));
    const acceptedLegal = body?.acceptedLegal === true;
    const acceptedLegalVersion = typeof body?.acceptedLegalVersion === 'string'
      ? body.acceptedLegalVersion.trim()
      : '';
    const acceptedAtClient = typeof body?.acceptedAt === 'string'
      ? body.acceptedAt.trim()
      : '';
    const _ALLOWED_FROM = new Set(['subscribe_page', 'email', 'social', 'ads']);
    const _fromRaw = typeof body?.acceptedFrom === 'string' ? body.acceptedFrom.trim() : '';
    const acceptedFrom = _ALLOWED_FROM.has(_fromRaw) ? _fromRaw : 'subscribe_page';
    const acceptedImmediateAccess = body?.acceptedImmediateAccess === true;
    const acceptedWithdrawalAcknowledgement = body?.acceptedWithdrawalAcknowledgement === true;

    if (!acceptedLegal || !acceptedLegalVersion || !acceptedImmediateAccess || !acceptedWithdrawalAcknowledgement) {
      return NextResponse.json({ error: 'Legal acceptance is required to subscribe.' }, { status: 400 });
    }

    const currentUser = await getCurrentUser();
    const acceptedAtServer = new Date().toISOString();

    const _emailRaw = typeof body.email === 'string' ? body.email.trim().toLowerCase() : '';
    const _emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const email = _emailRegex.test(_emailRaw) ? _emailRaw : undefined;

    const baseUrl = getBaseUrl();

    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      ...(email ? { customer_email: email } : {}),
      ...(currentUser?.id ? { client_reference_id: currentUser.id } : {}),
      line_items: [
        {
          price: process.env.STRIPE_PRICE_ID,
          quantity: 1,
        },
      ],
      metadata: {
        legal_accepted: 'true',
        legal_bundle_version: acceptedLegalVersion || LEGAL_BUNDLE_VERSION,
        legal_accepted_at_server: acceptedAtServer,
        legal_accepted_at_client: acceptedAtClient || acceptedAtServer,
        legal_accepted_from: acceptedFrom,
        legal_immediate_access_requested: acceptedImmediateAccess ? 'true' : 'false',
        legal_withdrawal_acknowledged: acceptedWithdrawalAcknowledgement ? 'true' : 'false',
        legal_user_id: currentUser?.id || '',
      },
      allow_promotion_codes: true,
      success_url: `${baseUrl}/subscribe/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${baseUrl}/subscribe`,
    });

    return NextResponse.json({ url: session.url });
  } catch (err) {
    console.error('Stripe checkout error:', err);
    return NextResponse.json({ error: 'Failed to create checkout session' }, { status: 500 });
  }
}
