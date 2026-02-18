import { NextResponse } from 'next/server';
import Stripe from 'stripe';
import { createSubscriber, updateSubscriberStatus } from '@/lib/subscribers';

function getStripe() {
  return new Stripe(process.env.STRIPE_SECRET_KEY!, {
    apiVersion: '2026-01-28.clover',
  });
}

export async function POST(request: Request) {
  const body = await request.text();
  const signature = request.headers.get('stripe-signature');

  if (!signature || !process.env.STRIPE_WEBHOOK_SECRET || !process.env.STRIPE_SECRET_KEY) {
    return NextResponse.json({ error: 'Missing signature or webhook secret' }, { status: 400 });
  }

  const stripe = getStripe();
  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, process.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    console.error('Webhook signature verification failed:', err);
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 });
  }

  switch (event.type) {
    case 'checkout.session.completed': {
      const session = event.data.object as Stripe.Checkout.Session;
      if (session.mode === 'subscription' && session.customer_email && session.customer && session.subscription) {
        const customerId = typeof session.customer === 'string' ? session.customer : session.customer.id;
        const subscriptionId = typeof session.subscription === 'string' ? session.subscription : session.subscription.id;
        createSubscriber({
          email: session.customer_email,
          stripe_customer_id: customerId,
          stripe_subscription_id: subscriptionId,
        });
      }
      break;
    }

    case 'customer.subscription.deleted': {
      const subscription = event.data.object as Stripe.Subscription;
      const subscriptionId = subscription.id;
      updateSubscriberStatus(subscriptionId, 'cancelled');
      break;
    }

    case 'invoice.payment_failed': {
      const invoice = event.data.object as Stripe.Invoice;
      const subDetails = invoice.parent?.subscription_details;
      if (subDetails?.subscription) {
        const subscriptionId = typeof subDetails.subscription === 'string' ? subDetails.subscription : subDetails.subscription.id;
        updateSubscriberStatus(subscriptionId, 'past_due');
      }
      break;
    }
  }

  return NextResponse.json({ received: true });
}
