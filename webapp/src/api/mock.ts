/**
 * In-browser implementation of the shop API used by the GitHub Pages demo.
 * Mirrors the backend's rules: server-side pricing from the shared catalog/pricing JSON,
 * the same validation errors and the same order status machine. Orders live in localStorage.
 */
import { calculateQuote, PricingError, type PricingRules } from '../domain/pricing';
import type {
  Catalog,
  CartItemIn,
  Order,
  OrderCreate,
  OrderCreated,
  OrderItem,
  OrderStatus,
  Quote,
  QuoteRequest,
} from '../domain/types';
import { useDemoInvoice } from './demoInvoice';
import { ApiError, type PaymentResult, type ShopApi } from './types';

const DEMO_USER_ID = 100_000_001;
const PHONE = /^\+?\d{10,15}$/;

interface StoredOrder extends Omit<Order, 'events' | 'status'> {
  /** Status history as [status, timestamp ms]. Future entries simulate the shop's progress. */
  timeline: [OrderStatus, number][];
}

export interface KeyValueStore {
  get(key: string): string | null;
  set(key: string, value: string): void;
}

const browserStore: KeyValueStore = {
  get: (k) => {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  set: (k, v) => {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* ignore */
    }
  },
};

const MIN = 60_000;

/** Simulated progress after an order is accepted, so the order history looks alive. */
function plannedProgress(order: StoredOrder, from: number): [OrderStatus, number][] {
  const tail: OrderStatus[] =
    order.deliveryMethod === 'courier'
      ? ['confirmed', 'in_delivery', 'completed']
      : ['confirmed', 'ready_for_pickup', 'completed'];
  return tail.map((s, i) => [s, from + (i === 0 ? 0.5 : i === 1 ? 3 : 15) * MIN]);
}

export class MockShopApi implements ShopApi {
  readonly mode = 'mock' as const;
  private readonly key = 'zernolist.demo.orders.v1';

  constructor(
    private readonly catalog: Catalog,
    private readonly rules: PricingRules,
    private readonly store: KeyValueStore = browserStore,
    private readonly now: () => number = Date.now,
    private readonly latencyMs = 250,
  ) {}

  private delay<T>(value: T): Promise<T> {
    if (this.latencyMs <= 0) return Promise.resolve(value);
    return new Promise((r) => setTimeout(() => r(value), this.latencyMs));
  }

  private load(): StoredOrder[] {
    try {
      return JSON.parse(this.store.get(this.key) ?? '[]') as StoredOrder[];
    } catch {
      return [];
    }
  }

  private save(orders: StoredOrder[]): void {
    this.store.set(this.key, JSON.stringify(orders));
  }

  private toOrder(o: StoredOrder): Order {
    const now = this.now();
    const events = o.timeline
      .filter(([, t]) => t <= now)
      .map(([status, t]) => ({ status, createdAt: new Date(t).toISOString() }));
    const { timeline: _timeline, ...rest } = o;
    void _timeline;
    return { ...rest, status: events.at(-1)?.status ?? 'new', events };
  }

  private resolve(items: CartItemIn[], lang: 'ru' | 'en'): OrderItem[] {
    const merged = new Map<string, OrderItem>();
    for (const item of items) {
      const product = this.catalog.products.find((p) => p.id === item.productId);
      if (!product) throw new ApiError(404, 'not_found', `Unknown product '${item.productId}'`);
      const variant = product.variants.find((v) => v.id === item.variantId);
      if (!variant) throw new ApiError(404, 'not_found', `Unknown variant '${item.variantId}'`);
      if (product.inStock === false)
        throw new ApiError(422, 'out_of_stock', `'${product.id}' is out of stock`);
      let grind: string | null = null;
      if (product.grindable) {
        const g = this.catalog.grindOptions.find((o) => o.id === (item.grind ?? 'beans'));
        if (!g) throw new ApiError(422, 'unknown_grind', `Unknown grind '${item.grind}'`);
        grind = g.id;
      } else if (item.grind) {
        throw new ApiError(422, 'unknown_grind', `'${product.id}' can't be ground`);
      }
      const key = `${product.id}|${variant.id}|${grind}`;
      const prev = merged.get(key);
      merged.set(key, {
        productId: product.id,
        variantId: variant.id,
        grind,
        title: product.name[lang],
        variantLabel: variant.label[lang],
        unitPrice: variant.price,
        quantity: item.quantity + (prev?.quantity ?? 0),
      });
    }
    return [...merged.values()];
  }

  private price(items: OrderItem[], req: QuoteRequest): Quote {
    try {
      return calculateQuote(items, req.deliveryMethod, req.promoCode, this.rules);
    } catch (e) {
      if (e instanceof PricingError) throw new ApiError(422, e.code, e.message);
      throw e;
    }
  }

  getCatalog(): Promise<Catalog> {
    return this.delay(this.catalog);
  }

  async quote(req: QuoteRequest): Promise<Quote> {
    return this.delay(this.price(this.resolve(req.items, 'ru'), req));
  }

  async createOrder(body: OrderCreate): Promise<OrderCreated> {
    const phone = body.customer.phone.replace(/[\s\-()]/g, '');
    if (!body.customer.name.trim()) throw new ApiError(422, 'invalid_request', 'Name is required');
    if (!PHONE.test(phone)) throw new ApiError(422, 'invalid_request', 'Invalid phone');
    if (body.deliveryMethod === 'courier' && !body.address?.trim())
      throw new ApiError(422, 'invalid_request', 'address is required for courier delivery');
    if (body.deliveryMethod === 'pickup') {
      if (!this.catalog.pickupPoints.some((p) => p.id === body.pickupPointId))
        throw new ApiError(422, 'invalid_request', 'Unknown pickup point');
    }
    const items = this.resolve(body.items, 'ru');
    const quote = this.price(items, body);
    if (body.promoCode?.trim() && quote.promoError)
      throw new ApiError(422, 'unknown_promo', 'Unknown promo code');

    const orders = this.load();
    const now = this.now();
    const paysWithStars = body.paymentMethod === 'stars';
    const stored: StoredOrder = {
      id: orders.reduce((m, o) => Math.max(m, o.id), 1000) + 1,
      userId: DEMO_USER_ID,
      source: 'api',
      customerName: body.customer.name.trim(),
      phone,
      deliveryMethod: body.deliveryMethod,
      address: body.deliveryMethod === 'courier' ? (body.address?.trim() ?? null) : null,
      pickupPointId: body.deliveryMethod === 'pickup' ? (body.pickupPointId ?? null) : null,
      deliverySlot: body.deliverySlot,
      comment: body.comment?.trim() || null,
      paymentMethod: body.paymentMethod,
      promoCode: quote.promoCode,
      subtotal: quote.subtotal,
      discount: quote.discount,
      deliveryFee: quote.deliveryFee,
      total: quote.total,
      starsAmount: paysWithStars ? quote.stars : null,
      createdAt: new Date(now).toISOString(),
      items,
      timeline: [[paysWithStars ? 'awaiting_payment' : 'new', now]],
    };
    if (!paysWithStars) stored.timeline.push(...plannedProgress(stored, now));
    this.save([stored, ...orders]);
    return this.delay({ order: this.toOrder(stored), invoiceUrl: null });
  }

  async listOrders(): Promise<Order[]> {
    return this.delay(this.load().map((o) => this.toOrder(o)));
  }

  async getOrder(id: number): Promise<Order> {
    const found = this.load().find((o) => o.id === id);
    if (!found) throw new ApiError(404, 'not_found', `Order #${id} not found`);
    return this.delay(this.toOrder(found));
  }

  /** Marks an order as paid — what the bot does on `successful_payment`. */
  markPaid(id: number): Order {
    const orders = this.load();
    const o = orders.find((x) => x.id === id);
    if (!o) throw new ApiError(404, 'not_found', `Order #${id} not found`);
    if (this.toOrder(o).status !== 'awaiting_payment')
      throw new ApiError(409, 'invalid_transition', 'Order is not awaiting payment');
    const now = this.now();
    o.timeline = [...o.timeline.filter(([, t]) => t <= now), ['paid', now]];
    o.timeline.push(...plannedProgress(o, now));
    this.save(orders);
    return this.toOrder(o);
  }

  async payOrder(order: Order): Promise<PaymentResult> {
    const result = await useDemoInvoice
      .getState()
      .open(`Zernolist #${order.id}`, order.starsAmount ?? 0);
    if (result === 'paid') this.markPaid(order.id);
    return result;
  }
}
