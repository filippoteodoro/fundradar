export const LEGAL_CONTROLLER_NAME =
  process.env.NEXT_PUBLIC_LEGAL_CONTROLLER_NAME || 'Fundradar';

export const LEGAL_CONTROLLER_EMAIL =
  process.env.NEXT_PUBLIC_LEGAL_CONTROLLER_EMAIL || '';

export const LEGAL_CONTROLLER_ADDRESS =
  process.env.NEXT_PUBLIC_LEGAL_CONTROLLER_ADDRESS || '';

export const LEGAL_JURISDICTION =
  process.env.NEXT_PUBLIC_LEGAL_JURISDICTION || 'Italy';

export const LEGAL_COMPANY_LEGAL_NAME =
  process.env.NEXT_PUBLIC_LEGAL_COMPANY_LEGAL_NAME || LEGAL_CONTROLLER_NAME;

export const LEGAL_VAT_ID =
  process.env.NEXT_PUBLIC_LEGAL_VAT_ID || '';

export const LEGAL_REA_NUMBER =
  process.env.NEXT_PUBLIC_LEGAL_REA_NUMBER || '';

export const LEGAL_PEC_EMAIL =
  process.env.NEXT_PUBLIC_LEGAL_PEC_EMAIL || '';

export const LEGAL_REGISTERED_CAPITAL =
  process.env.NEXT_PUBLIC_LEGAL_REGISTERED_CAPITAL || '';

export const LEGAL_DIGEST_UNSUBSCRIBE_EMAIL =
  process.env.NEXT_PUBLIC_LEGAL_DIGEST_UNSUBSCRIBE_EMAIL || LEGAL_CONTROLLER_EMAIL;

export const LEGAL_BILLING_PORTAL_URL =
  process.env.NEXT_PUBLIC_LEGAL_BILLING_PORTAL_URL || 'https://billing.stripe.com/p/login/3cIeVcalm8hwfmz6ac57W00';

// Bump when legal docs with contractual/privacy impact are materially changed.
export const LEGAL_BUNDLE_VERSION =
  process.env.NEXT_PUBLIC_LEGAL_BUNDLE_VERSION || '2026-02-21';
