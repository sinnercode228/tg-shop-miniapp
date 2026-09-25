import { bundledCatalog } from './data';
import { filterProducts, minPrice } from './search';

const products = bundledCatalog.products;

describe('filterProducts', () => {
  it('returns everything for an empty query', () => {
    expect(filterProducts(products, '  ', null)).toHaveLength(products.length);
  });
  it('filters by category', () => {
    const tea = filterProducts(products, '', 'tea');
    expect(tea.length).toBeGreaterThan(0);
    expect(tea.every((p) => p.categoryId === 'tea')).toBe(true);
  });
  it('matches russian and english names and tasting notes', () => {
    expect(filterProducts(products, 'кения', null).map((p) => p.id)).toContain('kenya-aa');
    expect(filterProducts(products, 'KENYA', null).map((p) => p.id)).toContain('kenya-aa');
    expect(filterProducts(products, 'жасмин', null).map((p) => p.id)).toContain(
      'ethiopia-yirgacheffe',
    );
  });
  it('requires all terms to match', () => {
    expect(filterProducts(products, 'кения чайник', null)).toEqual([]);
  });
  it('computes the lowest variant price', () => {
    const p = products[0]!;
    expect(minPrice(p)).toBe(Math.min(...p.variants.map((v) => v.price)));
  });
});
