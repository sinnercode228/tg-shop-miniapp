import type { Quote } from '../domain/types';
import { formatMoney, formatStars } from '../domain/money';
import { useT } from '../i18n';

export function Summary({
  quote,
  showDelivery = true,
  stars,
}: {
  quote: Pick<Quote, 'subtotal' | 'discount' | 'deliveryFee' | 'total'>;
  showDelivery?: boolean;
  stars?: number | null;
}) {
  const { t, lang } = useT();
  const row = 'flex justify-between py-1 text-[15px]';
  return (
    <div>
      <div className={row}>
        <span className="text-hint">{t('subtotal')}</span>
        <span className="tabular-nums">{formatMoney(quote.subtotal, lang)}</span>
      </div>
      {quote.discount > 0 && (
        <div className={row}>
          <span className="text-hint">{t('discount')}</span>
          <span className="text-emerald-600 tabular-nums dark:text-emerald-400">
            −{formatMoney(quote.discount, lang)}
          </span>
        </div>
      )}
      {showDelivery && (
        <div className={row}>
          <span className="text-hint">{t('delivery')}</span>
          <span className="tabular-nums">
            {quote.deliveryFee ? formatMoney(quote.deliveryFee, lang) : t('free')}
          </span>
        </div>
      )}
      <div className="mt-2 flex items-baseline justify-between border-t border-line pt-3 text-lg font-bold">
        <span>{t('total')}</span>
        <span className="tabular-nums">
          {formatMoney(quote.total, lang)}
          {stars ? (
            <span className="ml-2 text-sm font-semibold text-hint">
              ≈ {formatStars(stars, lang)} ⭐
            </span>
          ) : null}
        </span>
      </div>
    </div>
  );
}
