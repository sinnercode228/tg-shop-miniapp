import clsx from 'clsx';
import { motion } from 'motion/react';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { ProductArt } from '../components/ProductArt';
import { EmptyState, QuantityStepper, Section, Button } from '../components/ui';
import { pricingRules } from '../domain/data';
import { formatMoney } from '../domain/money';
import { useT } from '../i18n';
import { cartCount, useCart } from '../store/cart';
import { useCatalog } from '../store/catalog';
import { useBackButton, useMainButton } from '../telegram/hooks';
import { haptic } from '../telegram/sdk';

export function ProductPage() {
  const { id } = useParams();
  const { t, l, lang } = useT();
  const navigate = useNavigate();
  const catalog = useCatalog((s) => s.catalog);
  const add = useCart((s) => s.add);
  const count = useCart((s) => cartCount(s.lines));
  const product = catalog?.products.find((p) => p.id === id);

  const [variantId, setVariantId] = useState<string | null>(null);
  const [grind, setGrind] = useState('beans');
  const [qty, setQty] = useState(1);
  const [justAdded, setJustAdded] = useState(false);
  useBackButton(true, '/');

  const variant = product?.variants.find((v) => v.id === variantId) ?? product?.variants[0];
  const soldOut = product?.inStock === false;

  useMainButton(
    product && variant
      ? justAdded
        ? { text: `${t('cart')} · ${count}`, onClick: () => navigate('/cart') }
        : {
            text: soldOut ? t('outOfStock') : t('addToCart'),
            hint: formatMoney(variant.price * qty, lang),
            disabled: soldOut,
            onClick: () => {
              add(product.id, variant.id, product.grindable ? grind : null, qty);
              haptic.notify('success');
              setJustAdded(true);
            },
          }
      : null,
  );

  if (!catalog) return null;
  if (!product || !variant)
    return (
      <EmptyState
        icon="☕"
        title={t('nothingFound')}
        action={<Button onClick={() => navigate('/')}>{t('toCatalog')}</Button>}
      />
    );

  const touch = () => {
    haptic.selection();
    setJustAdded(false);
  };

  return (
    <div className="space-y-3">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="overflow-hidden rounded-3xl"
      >
        <ProductArt art={product.art} className="aspect-[4/3] w-full" />
      </motion.div>

      <Section>
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl leading-tight font-bold">{l(product.name)}</h1>
            <p className="mt-1 text-sm text-hint">{l(product.subtitle)}</p>
          </div>
          <div className="text-right text-xl font-bold tabular-nums">
            {formatMoney(variant.price, lang)}
          </div>
        </div>
        <p className="mt-3 text-[15px] leading-relaxed">{l(product.description)}</p>

        {(product.notes.length > 0 || product.roast) && (
          <dl className="mt-4 grid gap-3 border-t border-line pt-4 text-sm">
            {product.notes.length > 0 && (
              <div className="flex items-center gap-3">
                <dt className="w-20 shrink-0 text-hint">{t('notes')}</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {product.notes.map((n) => (
                    <span
                      key={n.en}
                      className="rounded-full bg-page px-2.5 py-1 text-xs font-medium"
                    >
                      {l(n)}
                    </span>
                  ))}
                </dd>
              </div>
            )}
            {product.roast ? (
              <div className="flex items-center gap-3">
                <dt className="w-20 shrink-0 text-hint">{t('roast')}</dt>
                <dd className="flex gap-1" aria-label={`${product.roast}/5`}>
                  {Array.from({ length: 5 }, (_, i) => (
                    <span
                      key={i}
                      className={clsx(
                        'h-2 w-6 rounded-full',
                        i < product.roast! ? 'bg-button' : 'bg-line',
                      )}
                    />
                  ))}
                </dd>
              </div>
            ) : null}
          </dl>
        )}
      </Section>

      {product.variants.length > 1 && (
        <Section title={t('size')}>
          <div className="grid grid-cols-2 gap-2">
            {product.variants.map((v) => (
              <OptionButton
                key={v.id}
                active={v.id === variant.id}
                onClick={() => {
                  touch();
                  setVariantId(v.id);
                }}
              >
                <span className="font-semibold">{l(v.label)}</span>
                <span className="text-xs text-hint tabular-nums">{formatMoney(v.price, lang)}</span>
              </OptionButton>
            ))}
          </div>
        </Section>
      )}

      {product.grindable && catalog.grindOptions.length > 0 && (
        <Section title={t('grind')}>
          <div className="grid grid-cols-2 gap-2">
            {catalog.grindOptions.map((g) => (
              <OptionButton
                key={g.id}
                active={g.id === grind}
                onClick={() => {
                  touch();
                  setGrind(g.id);
                }}
              >
                <span className="font-semibold">{l(g.name)}</span>
              </OptionButton>
            ))}
          </div>
        </Section>
      )}

      <Section>
        <div className="flex items-center justify-between">
          <span className="font-semibold">{t('quantity')}</span>
          <QuantityStepper
            value={qty}
            max={pricingRules.maxQuantityPerLine}
            onInc={() => {
              touch();
              setQty((q) => Math.min(pricingRules.maxQuantityPerLine, q + 1));
            }}
            onDec={() => {
              touch();
              setQty((q) => Math.max(1, q - 1));
            }}
          />
        </div>
      </Section>
    </div>
  );
}

function OptionButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={clsx(
        'pressable flex flex-col items-start rounded-xl border-2 px-3 py-2.5 text-left text-sm transition-colors',
        active ? 'border-button bg-button/8' : 'border-transparent bg-page',
      )}
    >
      {children}
    </button>
  );
}
