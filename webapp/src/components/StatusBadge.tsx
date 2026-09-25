import clsx from 'clsx';
import type { OrderStatus } from '../domain/types';
import { useT } from '../i18n';

const TONE: Record<OrderStatus, string> = {
  awaiting_payment: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  new: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  paid: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  confirmed: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  in_delivery: 'bg-violet-500/15 text-violet-700 dark:text-violet-300',
  ready_for_pickup: 'bg-violet-500/15 text-violet-700 dark:text-violet-300',
  completed: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  cancelled: 'bg-zinc-500/15 text-hint',
  refunded: 'bg-zinc-500/15 text-hint',
};

export function StatusBadge({ status }: { status: OrderStatus }) {
  const { t } = useT();
  return (
    <span
      className={clsx(
        'inline-flex h-6 items-center rounded-full px-2.5 text-xs font-semibold',
        TONE[status],
      )}
    >
      {t(`status_${status}`)}
    </span>
  );
}
