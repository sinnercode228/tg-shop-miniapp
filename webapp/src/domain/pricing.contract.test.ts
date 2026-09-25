import cases from '../../../shared/pricing-cases.json';
import { calculateQuote, PricingError, toStars } from './pricing';
import { pricingRules as rules } from './data';
import type { DeliveryMethod } from './types';

interface Case {
  name: string;
  lines: { unitPrice: number; quantity: number }[];
  delivery: DeliveryMethod;
  promo: string | null;
  expected?: Record<string, unknown>;
  error?: string;
}

describe('pricing contract (shared with pytest)', () => {
  for (const c of cases.cases as Case[]) {
    it(c.name, () => {
      if (c.error) {
        expect(() => calculateQuote(c.lines, c.delivery, c.promo, rules)).toThrow(PricingError);
        return;
      }
      expect(calculateQuote(c.lines, c.delivery, c.promo, rules)).toEqual(c.expected);
    });
  }

  it('rounds stars up', () => {
    expect(toStars(1, rules)).toBe(1);
    expect(toStars(rules.kopecksPerStar, rules)).toBe(1);
    expect(toStars(rules.kopecksPerStar + 1, rules)).toBe(2);
  });

  it('rejects empty carts and bad quantities', () => {
    expect(() => calculateQuote([], 'pickup', null, rules)).toThrow(/empty/);
    expect(() =>
      calculateQuote(
        [{ unitPrice: 100, quantity: rules.maxQuantityPerLine + 1 }],
        'pickup',
        null,
        rules,
      ),
    ).toThrow(PricingError);
  });
});
