import { formatMoney, formatStars } from './money';

const norm = (s: string) => s.replace(/\s/g, ' ');

describe('money formatting', () => {
  it('formats kopecks as whole roubles', () => {
    expect(norm(formatMoney(574200))).toBe('5 742 ₽');
  });

  it('groups Stars amounts per locale', () => {
    expect(norm(formatStars(3828))).toBe('3 828');
    expect(formatStars(3828, 'en')).toBe('3,828');
    expect(formatStars(90)).toBe('90');
  });
});
