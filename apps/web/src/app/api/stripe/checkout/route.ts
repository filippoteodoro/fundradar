import { NextResponse } from 'next/server';
import Stripe from 'stripe';

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
    const email = typeof body.email === 'string' && body.email.includes('@') ? body.email.toLowerCase() : undefined;

    const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000';

    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      ...(email ? { customer_email: email } : {}),
      line_items: [
        {
          price: process.env.STRIPE_PRICE_ID,
          quantity: 1,
        },
      ],
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
