import clsx from 'clsx';
import { AnimatePresence, motion } from 'motion/react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { ProductArt } from '../components/ProductArt';
import { EmptyState, Skeleton } from '../components/ui';
import { pricingRules } from '../domain/data';
import { calculateQuote } from '../domain/pricing';
import { formatMoney } from '../domain/money';
import { filterProducts, minPrice } from '../domain/search';
import type { Product } from '../domain/types';
import { useT } from '../i18n';
import { cartCount, resolveLines, useCart } from '../store/cart';
import { useCatalog } from '../store/catalog';
import { useMainButton } from '../telegram/hooks';
import { haptic } from '../telegram/sdk';

export function CatalogPage() {
  const { t, l, lang } = useT();
  const navigate = useNavigate();
  const catalog = useCatalog((s) => s.catalog);
  const lines = useCart((s) => s.lines);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string | null>(null);

  const products = useMemo(
    () => (catalog ? filterProducts(catalog.products, query, category) : []),
    [catalog, query, category],
  );

  const resolved = catalog ? resolveLines(lines, catalog) : [];
  const subtotal = resolved.length
    ? calculateQuote(
        resolved.map((r) => ({ unitPrice: r.variant.price, quantity: r.quantity })),
        'pickup',
        null,
        pricingRules,
      ).subtotal
    : 0;
  useMainButton(
    resolved.length
      ? {
          text: `${t('cart')} · ${cartCount(lines)}`,
          hint: formatMoney(subtotal, lang),
          onClick: () => navigate('/cart'),
        }
      : null,
  );

  return (
    <div className="space-y-4">
      <label className="relative block">
        <span className="sr-only">{t('search')}</span>
        <svg
          viewBox="0 0 24 24"
          className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-hint"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" strokeLinecap="round" />
        </svg>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('search')}
          className="h-12 w-full rounded-2xl bg-section pr-4 pl-11 text-[15px] outline-none placeholder:text-hint focus:ring-2 focus:ring-button/40"
        />
      </label>

      <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4" role="tablist">
        {[
          { id: null, label: t('all') },
          ...(catalog?.categories ?? []).map((c) => ({ id: c.id, label: l(c.name) })),
        ].map((c) => (
          <button
            key={c.id ?? 'all'}
            type="button"
            role="tab"
            aria-selected={category === c.id}
            onClick={() => {
              haptic.selection();
              setCategory(c.id);
            }}
            className={clsx(
              'pressable h-9 shrink-0 rounded-full px-4 text-sm font-semibold transition-colors',
              category === c.id ? 'bg-button text-button-fg' : 'bg-section text-fg',
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {!catalog ? (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="aspect-[3/4]" />
          ))}
        </div>
      ) : products.length === 0 ? (
        <EmptyState icon="🔎" title={t('nothingFound')} hint={t('tryAnother')} />
      ) : (
        <motion.ul layout className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <AnimatePresence initial={false}>
            {products.map((p) => (
              <motion.li
                key={p.id}
                layout
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ duration: 0.18 }}
              >
                <ProductCard product={p} />
              </motion.li>
            ))}
          </AnimatePresence>
        </motion.ul>
      )}
    </div>
  );
}

function ProductCard({ product }: { product: Product }) {
  const { t, l, lang } = useT();
  const add = useCart((s) => s.add);
  const inCart = useCart((s) =>
    s.lines.filter((x) => x.productId === product.id).reduce((n, x) => n + x.quantity, 0),
  );
  const soldOut = product.inStock === false;
  const first = product.variants[0]!;
  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-2xl bg-section">
      <Link to={`/product/${product.id}`} className="pressable block" aria-label={l(product.name)}>
        <ProductArt art={product.art} className="aspect-square w-full" />
        {product.badge === 'new' && (
          <span className="absolute top-2 left-2 rounded-full bg-button px-2 py-0.5 text-[10px] font-bold tracking-wide text-button-fg uppercase">
            {t('new')}
          </span>
        )}
        <div className="px-3 pt-2.5">
          <h3 className="line-clamp-2 text-[14px] leading-tight font-semibold">
            {l(product.name)}
          </h3>
          <p className="mt-0.5 line-clamp-1 text-[12px] text-hint">{l(product.subtitle)}</p>
        </div>
      </Link>
      <div className="mt-auto flex items-center justify-between px-3 pt-2 pb-3">
        <span className="text-[14px] font-bold tabular-nums">
          {product.variants.length > 1 && (
            <span className="font-normal text-hint">{t('from')} </span>
          )}
          {formatMoney(minPrice(product), lang)}
        </span>
        <button
          type="button"
          disabled={soldOut}
          aria-label={`${t('addToCart')}: ${l(product.name)}`}
          onClick={() => {
            haptic.impact('light');
            add(product.id, first.id, product.grindable ? 'beans' : null);
          }}
          className="pressable relative grid size-9 place-items-center rounded-full bg-button text-button-fg disabled:opacity-40"
        >
          <svg
            viewBox="0 0 24 24"
            className="size-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          {inCart > 0 && (
            <span className="absolute -top-1 -right-1 grid h-4.5 min-w-4.5 place-items-center rounded-full bg-fg px-1 text-[10px] font-bold text-page">
              {inCart}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
