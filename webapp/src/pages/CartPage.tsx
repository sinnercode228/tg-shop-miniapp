import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { ProductArt } from '../components/ProductArt';
import { Summary } from '../components/Summary';
import { Button, EmptyState, QuantityStepper, Section } from '../components/ui';
import { pricingRules } from '../domain/data';
import { formatMoney } from '../domain/money';
import { calculateQuote } from '../domain/pricing';
import { useT } from '../i18n';
import { resolveLines, useCart } from '../store/cart';
import { useCatalog } from '../store/catalog';
import { useBackButton, useMainButton } from '../telegram/hooks';
import { haptic } from '../telegram/sdk';

export function CartPage() {
  const { t, l, lang } = useT();
  const navigate = useNavigate();
  const catalog = useCatalog((s) => s.catalog);
  const { lines, increment, decrement, promoCode, setPromo } = useCart();
  const [promoInput, setPromoInput] = useState(promoCode);
  useBackButton(true, '/');

  const resolved = catalog ? resolveLines(lines, catalog) : [];
  const quote = resolved.length
    ? calculateQuote(
        resolved.map((r) => ({ unitPrice: r.variant.price, quantity: r.quantity })),
        'courier',
        promoCode,
        pricingRules,
      )
    : null;

  useMainButton(
    quote
      ? {
          text: t('checkout'),
          hint: formatMoney(quote.total, lang),
          onClick: () => navigate('/checkout'),
        }
      : null,
  );

  if (!catalog) return null;
  if (!quote) {
    return (
      <EmptyState
        icon="🛒"
        title={t('cartEmpty')}
        hint={t('cartEmptyHint')}
        action={<Button onClick={() => navigate('/')}>{t('toCatalog')}</Button>}
      />
    );
  }

  const grindName = (id: string | null) => catalog.grindOptions.find((g) => g.id === id);
  const afterDiscount = quote.subtotal - quote.discount;
  const progress = Math.min(1, afterDiscount / pricingRules.freeDeliveryThreshold);

  return (
    <div className="space-y-3">
      <h1 className="px-1 text-2xl font-bold">{t('cart')}</h1>
      <Section className="p-2">
        <ul>
          <AnimatePresence initial={false}>
            {resolved.map((line) => {
              const g = grindName(line.grind);
              return (
                <motion.li
                  key={line.key}
                  layout
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-3 overflow-hidden rounded-xl p-2"
                >
                  <Link
                    to={`/product/${line.productId}`}
                    aria-label={l(line.product.name)}
                    className="shrink-0"
                  >
                    <ProductArt art={line.product.art} className="size-16 rounded-xl" />
                  </Link>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-semibold">{l(line.product.name)}</div>
                    <div className="truncate text-xs text-hint">
                      {l(line.variant.label)}
                      {g ? ` · ${l(g.name)}` : ''}
                    </div>
                    <div className="mt-1 text-sm font-bold tabular-nums">
                      {formatMoney(line.lineTotal, lang)}
                    </div>
                  </div>
                  <QuantityStepper
                    size="sm"
                    value={line.quantity}
                    max={pricingRules.maxQuantityPerLine}
                    label={l(line.product.name)}
                    onInc={() => {
                      haptic.selection();
                      increment(line.key);
                    }}
                    onDec={() => {
                      haptic.impact(line.quantity === 1 ? 'medium' : 'light');
                      decrement(line.key);
                    }}
                  />
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      </Section>

      <Section>
        <div className="mb-2 text-sm">
          {quote.deliveryFee > 0
            ? t('freeDeliveryLeft', {
                amount: formatMoney(pricingRules.freeDeliveryThreshold - afterDiscount, lang),
              })
            : t('freeDeliveryReached')}
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-page">
          <motion.div
            className="h-full rounded-full bg-button"
            initial={false}
            animate={{ width: `${progress * 100}%` }}
          />
        </div>
      </Section>

      <Section title={t('promo')}>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setPromo(promoInput.trim());
            haptic.impact('light');
          }}
        >
          <input
            value={promoInput}
            onChange={(e) => setPromoInput(e.target.value.toUpperCase())}
            placeholder={t('promoPlaceholder')}
            aria-label={t('promo')}
            className="h-11 min-w-0 flex-1 rounded-xl bg-page px-3 font-mono uppercase outline-none focus:ring-2 focus:ring-button/40"
          />
          <Button type="submit" variant="soft">
            {t('apply')}
          </Button>
        </form>
        {promoCode && (
          <p
            className={
              quote.promoError
                ? 'mt-2 text-sm text-danger'
                : 'mt-2 text-sm text-emerald-600 dark:text-emerald-400'
            }
          >
            {quote.promoError ? t('promoUnknown') : `${t('promoApplied')}: ${quote.promoCode}`}
          </p>
        )}
      </Section>

      <Section>
        <Summary quote={quote} />
        <p className="mt-3 text-xs text-hint">{t('serverPriced')}</p>
      </Section>
    </div>
  );
}
