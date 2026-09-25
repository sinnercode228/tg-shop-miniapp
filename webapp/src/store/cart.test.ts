import { bundledCatalog as catalog, pricingRules } from '../domain/data';
import {
  addLine,
  cartCount,
  lineKey,
  resolveLines,
  setLineQuantity,
  toCartItems,
  useCart,
} from './cart';

describe('cart helpers', () => {
  it('adds a new line and merges identical ones', () => {
    let lines = addLine([], 'kenya-aa', '250g', 'filter');
    lines = addLine(lines, 'kenya-aa', '250g', 'filter', 2);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({ key: lineKey('kenya-aa', '250g', 'filter'), quantity: 3 });
  });

  it('keeps different grinds / variants as separate lines', () => {
    let lines = addLine([], 'kenya-aa', '250g', 'filter');
    lines = addLine(lines, 'kenya-aa', '250g', 'espresso');
    lines = addLine(lines, 'kenya-aa', '1kg', 'filter');
    expect(lines).toHaveLength(3);
    expect(cartCount(lines)).toBe(3);
  });

  it('clamps quantity to the per-line maximum', () => {
    const lines = addLine([], 'gaiwan', 'std', null, 999);
    expect(lines[0]?.quantity).toBe(pricingRules.maxQuantityPerLine);
  });

  it('ignores non-positive quantities for new lines', () => {
    expect(addLine([], 'gaiwan', 'std', null, 0)).toEqual([]);
  });

  it('removes a line when quantity drops to zero', () => {
    const lines = addLine([], 'gaiwan', 'std', null, 2);
    const key = lines[0]!.key;
    expect(setLineQuantity(lines, key, 1)[0]?.quantity).toBe(1);
    expect(setLineQuantity(lines, key, 0)).toEqual([]);
  });

  it('refuses to exceed the maximum number of lines', () => {
    let lines = addLine([], 'gaiwan', 'std', null);
    for (let i = 0; i < pricingRules.maxLines + 5; i++) {
      lines = addLine(lines, `p${i}`, 'v', null);
    }
    expect(lines).toHaveLength(pricingRules.maxLines);
  });

  it('resolves lines against the catalog and drops unknown products', () => {
    const lines = addLine(addLine([], 'kenya-aa', '1kg', 'beans', 2), 'ghost', 'x', null);
    const resolved = resolveLines(lines, catalog);
    expect(resolved).toHaveLength(1);
    const kenya = catalog.products.find((p) => p.id === 'kenya-aa')!;
    const kg = kenya.variants.find((v) => v.id === '1kg')!;
    expect(resolved[0]?.lineTotal).toBe(kg.price * 2);
  });

  it('serialises to API cart items without client prices', () => {
    const items = toCartItems(addLine([], 'gaiwan', 'std', null, 2));
    expect(items).toEqual([{ productId: 'gaiwan', variantId: 'std', grind: null, quantity: 2 }]);
  });
});

describe('useCart store', () => {
  beforeEach(() => useCart.getState().clear());

  it('supports increment / decrement / remove', () => {
    const { add } = useCart.getState();
    add('drip-morning', '5pcs', null);
    const key = useCart.getState().lines[0]!.key;
    useCart.getState().increment(key);
    expect(useCart.getState().lines[0]?.quantity).toBe(2);
    useCart.getState().decrement(key);
    useCart.getState().decrement(key);
    expect(useCart.getState().lines).toEqual([]);
    add('drip-morning', '5pcs', null);
    useCart.getState().remove(useCart.getState().lines[0]!.key);
    expect(useCart.getState().lines).toEqual([]);
  });

  it('persists to localStorage and clears the promo on clear()', () => {
    useCart.getState().add('gaiwan', 'std', null);
    useCart.getState().setPromo('ZERNO10');
    const saved = JSON.parse(localStorage.getItem('zernolist.cart.v1') ?? '{}');
    expect(saved.state.lines).toHaveLength(1);
    expect(saved.state.promoCode).toBe('ZERNO10');
    useCart.getState().clear();
    expect(useCart.getState().promoCode).toBe('');
  });
});
