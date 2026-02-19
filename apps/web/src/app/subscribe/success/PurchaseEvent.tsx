'use client';

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { SUBSCRIPTION_PRICE_EUR, SUBSCRIPTION_PRODUCT_NAME } from '@/lib/pricing';

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
          value: Number(SUBSCRIPTION_PRICE_EUR.toFixed(2)),
          currency: 'EUR',
          items: [{
            item_name: SUBSCRIPTION_PRODUCT_NAME,
            price: Number(SUBSCRIPTION_PRICE_EUR.toFixed(2)),
            quantity: 1,
          }],
        },
      });
  }, [searchParams]);

  return null;
}
