/**
 * Pure pricing logic — a line-by-line mirror of `bot/tgshop/domain/pricing.py`.
 * Parity is enforced by the shared vectors in `shared/pricing-cases.json`.
 * The backend always re-prices orders; the client uses this for instant UI feedback
 * and the in-browser demo API.
 */
import type { DeliveryMethod, Quote } from './types';

export type Promo =
  | { code: string; kind: 'percent'; value: number; maxDiscount: number | null }
  | { code: string; kind: 'free_delivery' };

export interface PricingRules {
  courierFee: number;
  freeDeliveryThreshold: number;
  maxQuantityPerLine: number;
  maxLines: number;
  kopecksPerStar: number;
  promoCodes: Record<string, Promo>;
}

interface RawPricing {
  courierFee: number;
  freeDeliveryThreshold: number;
  maxQuantityPerLine: number;
  maxLines: number;
  kopecksPerStar: number;
  promoCodes?: Record<string, { kind: string; value?: number; maxDiscount?: number }>;
}

export function rulesFromJson(raw: RawPricing): PricingRules {
  const promoCodes: Record<string, Promo> = {};
  for (const [code, spec] of Object.entries(raw.promoCodes ?? {})) {
    const upper = code.toUpperCase();
    promoCodes[upper] =
      spec.kind === 'percent'
        ? {
            code: upper,
            kind: 'percent',
            value: spec.value ?? 0,
            maxDiscount: spec.maxDiscount ?? null,
          }
        : { code: upper, kind: 'free_delivery' };
  }
  return {
    courierFee: raw.courierFee,
    freeDeliveryThreshold: raw.freeDeliveryThreshold,
    maxQuantityPerLine: raw.maxQuantityPerLine,
    maxLines: raw.maxLines,
    kopecksPerStar: raw.kopecksPerStar,
    promoCodes,
  };
}

export interface PricedLine {
  unitPrice: number;
  quantity: number;
}

export class PricingError extends Error {
  constructor(
    message: string,
    readonly code: 'cart_empty' | 'cart_too_large' | 'bad_quantity' | 'bad_price',
  ) {
    super(message);
    this.name = 'PricingError';
  }
}

export const normalizePromo = (raw: string | null | undefined): string =>
  (raw ?? '').trim().toUpperCase();

/** Kopecks → Telegram Stars, rounded up (in the shop's favour), integer-only. */
export const toStars = (amount: number, rules: PricingRules): number =>
  Math.ceil(amount / rules.kopecksPerStar);

export function validateLines(lines: readonly PricedLine[], rules: PricingRules): void {
  if (lines.length === 0) throw new PricingError('Cart is empty', 'cart_empty');
  if (lines.length > rules.maxLines)
    throw new PricingError(`Too many items (max ${rules.maxLines})`, 'cart_too_large');
  for (const line of lines) {
    if (
      !Number.isInteger(line.quantity) ||
      line.quantity < 1 ||
      line.quantity > rules.maxQuantityPerLine
    )
      throw new PricingError(
        `Quantity must be between 1 and ${rules.maxQuantityPerLine}`,
        'bad_quantity',
      );
    if (line.unitPrice < 0) throw new PricingError('Negative price', 'bad_price');
  }
}

export function calculateQuote(
  lines: readonly PricedLine[],
  delivery: DeliveryMethod,
  promoCode: string | null | undefined,
  rules: PricingRules,
): Quote {
  validateLines(lines, rules);
  const subtotal = lines.reduce((sum, l) => sum + l.unitPrice * l.quantity, 0);

  const code = normalizePromo(promoCode);
  const promo = code ? rules.promoCodes[code] : undefined;

  let discount = 0;
  if (promo?.kind === 'percent') {
    // Percent discounts are rounded down to whole roubles.
    discount = Math.floor(Math.floor((subtotal * promo.value) / 100) / 100) * 100;
    if (promo.maxDiscount !== null) discount = Math.min(discount, promo.maxDiscount);
  }

  const afterDiscount = subtotal - discount;
  const deliveryFee =
    delivery === 'courier' &&
    promo?.kind !== 'free_delivery' &&
    afterDiscount < rules.freeDeliveryThreshold
      ? rules.courierFee
      : 0;

  const total = afterDiscount + deliveryFee;
  return {
    subtotal,
    discount,
    deliveryFee,
    total,
    stars: toStars(total, rules),
    promoCode: promo ? promo.code : null,
    promoError: code && !promo ? 'unknown' : null,
  };
}
