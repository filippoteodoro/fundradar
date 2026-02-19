const parsedPrice = Number(process.env.NEXT_PUBLIC_SUBSCRIPTION_PRICE_EUR || '9');

export const SUBSCRIPTION_PRICE_EUR = Number.isFinite(parsedPrice) && parsedPrice > 0
  ? parsedPrice
  : 9;

export const SUBSCRIPTION_PRODUCT_NAME = 'Fundradar Weekly Signals';
