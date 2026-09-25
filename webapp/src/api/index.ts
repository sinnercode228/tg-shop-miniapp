import { bundledCatalog, pricingRules } from '../domain/data';
import { HttpShopApi } from './http';
import { MockShopApi } from './mock';
import type { ShopApi } from './types';

/**
 * `VITE_API_MODE=http` talks to the FastAPI backend (`VITE_API_URL`, default same origin);
 * anything else uses the in-browser demo API (GitHub Pages build).
 */
export function createApi(env: ImportMetaEnv = import.meta.env): ShopApi {
  if (env.VITE_API_MODE === 'http') {
    return new HttpShopApi((env.VITE_API_URL ?? '').replace(/\/$/, ''));
  }
  return new MockShopApi(bundledCatalog, pricingRules);
}

export const api: ShopApi = createApi();
export { ApiError } from './types';
export type { PaymentResult, ShopApi } from './types';
