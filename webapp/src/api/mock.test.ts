import { bundledCatalog, pricingRules } from '../domain/data';
import type { OrderCreate } from '../domain/types';
import { MockShopApi, type KeyValueStore } from './mock';
import { ApiError } from './types';

function memoryStore(): KeyValueStore {
  const m = new Map<string, string>();
  return { get: (k) => m.get(k) ?? null, set: (k, v) => void m.set(k, v) };
}

const base: OrderCreate = {
  items: [{ productId: 'kenya-aa', variantId: '250g', grind: 'filter', quantity: 2 }],
  deliveryMethod: 'pickup',
  pickupPointId: 'kofeynaya-12',
  deliverySlot: 'asap',
  paymentMethod: 'on_receipt',
  customer: { name: 'Анна', phone: '+7 (900) 000-00-00' },
};

describe('MockShopApi', () => {
  let now = Date.parse('2026-01-01T10:00:00Z');
  const make = () => new MockShopApi(bundledCatalog, pricingRules, memoryStore(), () => now, 0);

  it('prices from the catalog, not from the client', async () => {
    const api = make();
    const kenya = bundledCatalog.products.find((p) => p.id === 'kenya-aa')!;
    const quote = await api.quote({ items: base.items, deliveryMethod: 'pickup' });
    expect(quote.subtotal).toBe(kenya.variants[0]!.price * 2);
    expect(quote.deliveryFee).toBe(0);
  });

  it('creates a pay-on-receipt order that progresses over time', async () => {
    const api = make();
    const { order } = await api.createOrder(base);
    expect(order.status).toBe('new');
    expect(order.phone).toBe('+79000000000');
    expect(order.items[0]).toMatchObject({ grind: 'filter', quantity: 2 });
    now += 60 * 60_000;
    const later = await api.getOrder(order.id);
    expect(later.status).toBe('completed');
    expect(later.events.map((e) => e.status)).toEqual([
      'new',
      'confirmed',
      'ready_for_pickup',
      'completed',
    ]);
  });

  it('keeps Stars orders awaiting payment until paid', async () => {
    const api = make();
    const { order } = await api.createOrder({ ...base, paymentMethod: 'stars' });
    expect(order.status).toBe('awaiting_payment');
    expect(order.starsAmount).toBe(Math.ceil(order.total / pricingRules.kopecksPerStar));
    expect(api.markPaid(order.id).status).toBe('paid');
    expect(() => api.markPaid(order.id)).toThrow(ApiError);
  });

  it('validates delivery details, phone and promo codes', async () => {
    const api = make();
    await expect(
      api.createOrder({ ...base, deliveryMethod: 'courier', address: '' }),
    ).rejects.toMatchObject({ code: 'invalid_request' });
    await expect(
      api.createOrder({ ...base, customer: { name: 'A', phone: '123' } }),
    ).rejects.toBeInstanceOf(ApiError);
    await expect(api.createOrder({ ...base, promoCode: 'NOPE' })).rejects.toMatchObject({
      code: 'unknown_promo',
    });
    await expect(
      api.createOrder({
        ...base,
        items: [{ productId: 'gaiwan', variantId: 'std', grind: 'filter', quantity: 1 }],
      }),
    ).rejects.toMatchObject({ code: 'unknown_grind' });
  });

  it('lists newest orders first with increasing ids', async () => {
    const api = make();
    const a = await api.createOrder(base);
    const b = await api.createOrder(base);
    expect(b.order.id).toBe(a.order.id + 1);
    expect((await api.listOrders()).map((o) => o.id)).toEqual([b.order.id, a.order.id]);
  });
});
