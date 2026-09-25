import type { Lang } from './types';

const formatters = new Map<Lang, Intl.NumberFormat>();

/** Kopecks → "1 290 ₽". Whole roubles are shown without decimals. */
export function formatMoney(kopecks: number, lang: Lang = 'ru'): string {
  let fmt = formatters.get(lang);
  if (!fmt) {
    fmt = new Intl.NumberFormat(lang === 'ru' ? 'ru-RU' : 'en-US', {
      style: 'currency',
      currency: 'RUB',
      currencyDisplay: 'narrowSymbol',
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
    formatters.set(lang, fmt);
  }
  return fmt.format(kopecks / 100);
}

/** 3828 → "3 828" (ru) / "3,828" (en). */
export function formatStars(stars: number, lang: Lang = 'ru'): string {
  return new Intl.NumberFormat(lang === 'ru' ? 'ru-RU' : 'en-US').format(stars);
}
