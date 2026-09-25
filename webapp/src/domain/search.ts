import type { Product } from './types';

const norm = (s: string) => s.toLowerCase().replaceAll('ё', 'е').trim();

/** Case/ё-insensitive search across names, subtitles and tasting notes in both languages. */
export function filterProducts(
  products: readonly Product[],
  query: string,
  categoryId: string | null,
): Product[] {
  const terms = norm(query).split(/\s+/).filter(Boolean);
  return products.filter((p) => {
    if (categoryId && p.categoryId !== categoryId) return false;
    if (terms.length === 0) return true;
    const haystack = norm(
      [
        p.name.ru,
        p.name.en,
        p.subtitle.ru,
        p.subtitle.en,
        ...p.notes.flatMap((n) => [n.ru, n.en]),
      ].join(' '),
    );
    return terms.every((term) => haystack.includes(term));
  });
}

export const minPrice = (p: Product): number => Math.min(...p.variants.map((v) => v.price));
