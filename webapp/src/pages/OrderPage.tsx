import clsx from 'clsx';
import { motion } from 'motion/react';
import { useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { api, ApiError } from '../api';
import { StatusBadge } from '../components/StatusBadge';
import { Summary } from '../components/Summary';
import { Button, EmptyState, Section, Skeleton } from '../components/ui';
import { formatMoney, formatStars } from '../domain/money';
import { useAsync } from '../hooks/useAsync';
import { useT } from '../i18n';
import { useCatalog } from '../store/catalog';
import { useBackButton, useMainButton } from '../telegram/hooks';
import { haptic } from '../telegram/sdk';

export function OrderPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const { t, l, lang } = useT();
  const navigate = useNavigate();
  const catalog = useCatalog((s) => s.catalog);
  const [paying, setPaying] = useState(false);
  const [cancelledNote, setCancelledNote] = useState(params.get('payment') === 'cancelled');
  const { data: order, error, reload } = useAsync(() => api.getOrder(Number(id)), `order:${id}`);
  const placed = params.get('placed') === '1';
  useBackButton(true, placed ? '/' : '/orders');

  const pay = async () => {
    if (!order) return;
    setPaying(true);
    const result = await api.payOrder(order).catch(() => 'failed' as const);
    setPaying(false);
    setCancelledNote(result !== 'paid');
    haptic.notify(result === 'paid' ? 'success' : 'warning');
    reload();
  };

  useMainButton(
    order?.status === 'awaiting_payment'
      ? {
          text: t('payStars', { stars: formatStars(order.starsAmount ?? 0, lang) }),
          progress: paying,
          onClick: () => void pay(),
        }
      : placed
        ? { text: t('goShopping'), onClick: () => navigate('/') }
        : null,
  );

  if (error instanceof ApiError && error.status === 404)
    return (
      <EmptyState
        icon="🧾"
        title={t('orderNotFound')}
        action={<Button onClick={() => navigate('/orders')}>{t('orders')}</Button>}
      />
    );
  if (error)
    return (
      <EmptyState
        icon="⚠️"
        title={t('error')}
        hint={error.message}
        action={<Button onClick={reload}>{t('retry')}</Button>}
      />
    );
  if (!order) return <Skeleton className="h-64" />;

  const awaiting = order.status === 'awaiting_payment';
  const headline = awaiting
    ? t('awaitingPayment')
    : order.events.some((e) => e.status === 'paid')
      ? t('orderPaid')
      : t('orderPlaced');
  const time = new Intl.DateTimeFormat(lang === 'ru' ? 'ru-RU' : 'en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    day: 'numeric',
    month: 'short',
  });
  const point = catalog?.pickupPoints.find((p) => p.id === order.pickupPointId);
  const grind = (gid: string | null) => catalog?.grindOptions.find((g) => g.id === gid);

  return (
    <div className="space-y-3">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex flex-col items-center rounded-3xl bg-section px-6 py-8 text-center"
      >
        <motion.div
          initial={{ scale: 0, rotate: -20 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 14, delay: 0.1 }}
          className={clsx(
            'grid size-18 place-items-center rounded-full text-4xl',
            awaiting ? 'bg-amber-400/20' : 'bg-emerald-500/15',
          )}
        >
          {awaiting ? '⭐' : '✓'}
        </motion.div>
        <h1 className="mt-4 text-2xl font-bold">{headline}</h1>
        <p className="mt-1 text-hint">
          {t('order')} #{order.id} · {formatMoney(order.total, lang)}
        </p>
        {placed && !awaiting && <p className="mt-3 text-sm">{t('thanks')}</p>}
        {cancelledNote && awaiting && (
          <p className="mt-3 rounded-xl bg-amber-400/15 p-3 text-sm">{t('paymentCancelled')}</p>
        )}
      </motion.div>

      <Section title={t('delivery')}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-semibold">
              {order.deliveryMethod === 'courier' ? `🛵 ${t('courier')}` : `🏪 ${t('pickup')}`}
            </div>
            <div className="text-sm text-hint">
              {order.deliveryMethod === 'courier'
                ? order.address
                : point
                  ? `${l(point.name)} · ${l(point.hours)}`
                  : order.pickupPointId}
            </div>
            <div className="text-sm text-hint">{t(`slot_${order.deliverySlot}`)}</div>
          </div>
          <StatusBadge status={order.status} />
        </div>
        <ol className="mt-4 space-y-3 border-l-2 border-line pl-4">
          {order.events.map((e, i) => (
            <li key={`${e.status}-${i}`} className="relative">
              <span
                className={clsx(
                  'absolute top-1.5 -left-[24px] size-3 rounded-full ring-4 ring-section',
                  i === order.events.length - 1 ? 'bg-button' : 'bg-hint',
                )}
              />
              <div className="text-sm font-semibold">{t(`status_${e.status}`)}</div>
              <div className="text-xs text-hint">{time.format(new Date(e.createdAt))}</div>
            </li>
          ))}
        </ol>
      </Section>

      <Section title={t('items')}>
        <ul className="divide-y divide-line">
          {order.items.map((it) => {
            const g = grind(it.grind);
            const product = catalog?.products.find((p) => p.id === it.productId);
            return (
              <li
                key={`${it.productId}-${it.variantId}-${it.grind}`}
                className="flex justify-between gap-3 py-2 text-sm"
              >
                <span>
                  <span className="font-semibold">{product ? l(product.name) : it.title}</span>
                  <span className="block text-xs text-hint">
                    {it.variantLabel}
                    {g ? ` · ${l(g.name)}` : ''} · {t('itemsCount', { n: it.quantity })}
                  </span>
                </span>
                <span className="tabular-nums">
                  {formatMoney(it.unitPrice * it.quantity, lang)}
                </span>
              </li>
            );
          })}
        </ul>
        <div className="mt-3 border-t border-line pt-3">
          <Summary quote={order} stars={order.starsAmount} />
        </div>
        <p className="mt-3 text-xs text-hint">
          {t('payment')}: {t(order.paymentMethod === 'stars' ? 'pay_stars' : 'pay_on_receipt')}
          {order.promoCode ? ` · ${t('promo')}: ${order.promoCode}` : ''}
        </p>
      </Section>
    </div>
  );
}
