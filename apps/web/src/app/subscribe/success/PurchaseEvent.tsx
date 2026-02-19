'use client';

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';

export function PurchaseEvent() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const sessionId = searchParams.get('session_id');
    if (!sessionId) return;

    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({
      event: 'purchase',
      ecommerce: {
        transaction_id: sessionId,
        value: 9.00,
        currency: 'EUR',
        items: [{ item_name: 'Fundradar Weekly Signals', price: 9.00, quantity: 1 }],
      },
    });
  }, [searchParams]);

  return null;
}
