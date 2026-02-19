'use client';

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';

export function PurchaseEvent() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const sessionId = searchParams.get('session_id');
    if (!sessionId) return;

    const w = window as unknown as Window & { dataLayer: object[] };
    w.dataLayer = w.dataLayer || [];
    w.dataLayer.push({
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
