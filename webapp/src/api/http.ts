import type {
  Catalog,
  Order,
  OrderCreate,
  OrderCreated,
  Quote,
  QuoteRequest,
} from '../domain/types';
import { getWebApp } from '../telegram/sdk';
import { ApiError, type PaymentResult, type ShopApi } from './types';

/** REST client for the FastAPI backend. Auth: `Authorization: tma <initData>` (HMAC-checked). */
export class HttpShopApi implements ShopApi {
  readonly mode = 'http' as const;

  constructor(
    private readonly baseUrl: string,
    private readonly initData: () => string = () => getWebApp()?.initData ?? '',
    private readonly fetchImpl: typeof fetch = (...args) => fetch(...args),
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body) headers.set('Content-Type', 'application/json');
    const initData = this.initData();
    if (initData) headers.set('Authorization', `tma ${initData}`);
    const res = await this.fetchImpl(`${this.baseUrl}/api${path}`, { ...init, headers });
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const err = (body as { error?: { code?: string; message?: string } } | null)?.error;
      throw new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? res.statusText);
    }
    return body as T;
  }

  getCatalog = () => this.request<Catalog>('/catalog');
  quote = (req: QuoteRequest) =>
    this.request<Quote>('/quote', { method: 'POST', body: JSON.stringify(req) });
  createOrder = (body: OrderCreate) =>
    this.request<OrderCreated>('/orders', { method: 'POST', body: JSON.stringify(body) });
  listOrders = () => this.request<Order[]>('/orders');
  getOrder = (id: number) => this.request<Order>(`/orders/${id}`);

  async payOrder(order: Order, invoiceUrl?: string | null): Promise<PaymentResult> {
    const wa = getWebApp();
    if (!wa?.initData) throw new ApiError(400, 'not_in_telegram', 'Stars payments need Telegram');
    const url =
      invoiceUrl ??
      (
        await this.request<{ invoiceUrl: string }>(`/orders/${order.id}/invoice`, {
          method: 'POST',
        })
      ).invoiceUrl;
    return new Promise((resolve) => wa.openInvoice(url, (status) => resolve(status)));
  }
}
