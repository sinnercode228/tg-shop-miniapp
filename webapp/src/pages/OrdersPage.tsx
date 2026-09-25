import { motion } from 'motion/react';
import { Link, useNavigate } from 'react-router';
import { api } from '../api';
import { StatusBadge } from '../components/StatusBadge';
import { Button, EmptyState, Skeleton } from '../components/ui';
import { useAsync } from '../hooks/useAsync';
import { formatMoney } from '../domain/money';
import { useT } from '../i18n';
import { useBackButton } from '../telegram/hooks';

export function OrdersPage() {
  const { t, lang } = useT();
  const navigate = useNavigate();
  const { data: orders, error, reload } = useAsync(() => api.listOrders(), 'orders');
  useBackButton(true, '/');

  if (error)
    return (
      <EmptyState
        icon="⚠️"
        title={t('error')}
        hint={error.message}
        action={<Button onClick={reload}>{t('retry')}</Button>}
      />
    );
  if (!orders)
    return (
      <div className="space-y-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );
  if (orders.length === 0)
    return (
      <EmptyState
        icon="🧾"
        title={t('noOrders')}
        hint={t('noOrdersHint')}
        action={<Button onClick={() => navigate('/')}>{t('goShopping')}</Button>}
      />
    );

  const dateFmt = new Intl.DateTimeFormat(lang === 'ru' ? 'ru-RU' : 'en-GB', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
  return (
    <div className="space-y-3">
      <h1 className="px-1 text-2xl font-bold">{t('orders')}</h1>
      <ul className="space-y-2">
        {orders.map((o, i) => (
          <motion.li
            key={o.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03 }}
          >
            <Link to={`/orders/${o.id}`} className="pressable block rounded-2xl bg-section p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold">
                  {t('order')} #{o.id}
                </span>
                <StatusBadge status={o.status} />
              </div>
              <div className="mt-1 truncate text-sm text-hint">
                {o.items.map((it) => `${it.title} × ${it.quantity}`).join(', ')}
              </div>
              <div className="mt-2 flex items-center justify-between text-sm">
                <span className="text-hint">{dateFmt.format(new Date(o.createdAt))}</span>
                <span className="font-bold tabular-nums">{formatMoney(o.total, lang)}</span>
              </div>
            </Link>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}
