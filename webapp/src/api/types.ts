import type {
  Catalog,
  Order,
  OrderCreate,
  OrderCreated,
  Quote,
  QuoteRequest,
} from '../domain/types';

export type PaymentResult = 'paid' | 'cancelled' | 'failed' | 'pending';

/** Everything the UI needs from a backend. Implemented by the HTTP client and the demo mock. */
export interface ShopApi {
  readonly mode: 'http' | 'mock';
  getCatalog(): Promise<Catalog>;
  quote(req: QuoteRequest): Promise<Quote>;
  createOrder(body: OrderCreate): Promise<OrderCreated>;
  listOrders(): Promise<Order[]>;
  getOrder(id: number): Promise<Order>;
  /** Runs the Telegram Stars payment for an order awaiting payment. */
  payOrder(order: Order, invoiceUrl?: string | null): Promise<PaymentResult>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
