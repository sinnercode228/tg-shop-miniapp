import { create } from 'zustand';
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware';
import { pricingRules } from '../domain/data';
import type { CartItemIn, Catalog, Product, Variant } from '../domain/types';

export interface CartLine {
  key: string;
  productId: string;
  variantId: string;
  grind: string | null;
  quantity: number;
}

export const lineKey = (productId: string, variantId: string, grind: string | null): string =>
  [productId, variantId, grind ?? '-'].join('|');

const clampQty = (q: number, max = pricingRules.maxQuantityPerLine) =>
  Math.max(0, Math.min(max, Math.trunc(q)));

export interface CartState {
  lines: CartLine[];
  promoCode: string;
  add(productId: string, variantId: string, grind: string | null, quantity?: number): void;
  setQuantity(key: string, quantity: number): void;
  increment(key: string): void;
  decrement(key: string): void;
  remove(key: string): void;
  setPromo(code: string): void;
  clear(): void;
}

/** Pure reducer-style helpers (unit-tested without React). */
export function addLine(
  lines: CartLine[],
  productId: string,
  variantId: string,
  grind: string | null,
  quantity = 1,
): CartLine[] {
  const key = lineKey(productId, variantId, grind);
  const existing = lines.find((l) => l.key === key);
  if (existing) {
    return lines.map((l) =>
      l.key === key ? { ...l, quantity: clampQty(l.quantity + quantity) } : l,
    );
  }
  if (lines.length >= pricingRules.maxLines) return lines;
  const q = clampQty(quantity);
  return q > 0 ? [...lines, { key, productId, variantId, grind, quantity: q }] : lines;
}

export function setLineQuantity(lines: CartLine[], key: string, quantity: number): CartLine[] {
  const q = clampQty(quantity);
  return q === 0
    ? lines.filter((l) => l.key !== key)
    : lines.map((l) => (l.key === key ? { ...l, quantity: q } : l));
}

const safeStorage: StateStorage = {
  getItem: (name) => {
    try {
      return localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      localStorage.setItem(name, value);
    } catch {
      /* private mode / quota — cart simply isn't persisted */
    }
  },
  removeItem: (name) => {
    try {
      localStorage.removeItem(name);
    } catch {
      /* ignore */
    }
  },
};

export const useCart = create<CartState>()(
  persist(
    (set, get) => ({
      lines: [],
      promoCode: '',
      add: (productId, variantId, grind, quantity = 1) =>
        set({ lines: addLine(get().lines, productId, variantId, grind, quantity) }),
      setQuantity: (key, quantity) => set({ lines: setLineQuantity(get().lines, key, quantity) }),
      increment: (key) => {
        const line = get().lines.find((l) => l.key === key);
        if (line) set({ lines: setLineQuantity(get().lines, key, line.quantity + 1) });
      },
      decrement: (key) => {
        const line = get().lines.find((l) => l.key === key);
        if (line) set({ lines: setLineQuantity(get().lines, key, line.quantity - 1) });
      },
      remove: (key) => set({ lines: get().lines.filter((l) => l.key !== key) }),
      setPromo: (promoCode) => set({ promoCode }),
      clear: () => set({ lines: [], promoCode: '' }),
    }),
    { name: 'zernolist.cart.v1', storage: createJSONStorage(() => safeStorage), version: 1 },
  ),
);

export interface ResolvedLine extends CartLine {
  product: Product;
  variant: Variant;
  lineTotal: number;
}

/** Joins cart lines with the catalog, silently dropping lines whose product disappeared. */
export function resolveLines(lines: readonly CartLine[], catalog: Catalog): ResolvedLine[] {
  const byId = new Map(catalog.products.map((p) => [p.id, p]));
  const out: ResolvedLine[] = [];
  for (const line of lines) {
    const product = byId.get(line.productId);
    const variant = product?.variants.find((v) => v.id === line.variantId);
    if (!product || !variant || product.inStock === false) continue;
    out.push({ ...line, product, variant, lineTotal: variant.price * line.quantity });
  }
  return out;
}

export const cartCount = (lines: readonly CartLine[]): number =>
  lines.reduce((n, l) => n + l.quantity, 0);

export const toCartItems = (lines: readonly CartLine[]): CartItemIn[] =>
  lines.map(({ productId, variantId, grind, quantity }) => ({
    productId,
    variantId,
    grind,
    quantity,
  }));
