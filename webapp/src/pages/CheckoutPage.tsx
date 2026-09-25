import clsx from 'clsx';
import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router';
import { api, ApiError } from '../api';
import { Summary } from '../components/Summary';
import { Section, Segmented } from '../components/ui';
import { formatMoney, formatStars } from '../domain/money';
import type { DeliveryMethod, DeliverySlot, PaymentMethod, Quote } from '../domain/types';
import { useT } from '../i18n';
import { toCartItems, useCart } from '../store/cart';
import { useCatalog } from '../store/catalog';
import { useBackButton, useMainButton } from '../telegram/hooks';
import { getWebApp, haptic } from '../telegram/sdk';

const PHONE = /^\+?\d{10,15}$/;
const DRAFT_KEY = 'zernolist.checkout.v1';

interface Draft {
  delivery: DeliveryMethod;
  address: string;
  pickupPointId: string;
  slot: DeliverySlot;
  name: string;
  phone: string;
  comment: string;
  payment: PaymentMethod;
}

function loadDraft(): Draft {
  const fallback: Draft = {
    delivery: 'courier',
    address: '',
    pickupPointId: '',
    slot: 'asap',
    name: getWebApp()?.initDataUnsafe.user?.first_name ?? '',
    phone: '',
    comment: '',
    payment: 'stars',
  };
  try {
    return {
      ...fallback,
      ...(JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? '{}') as Partial<Draft>),
    };
  } catch {
    return fallback;
  }
}

export function CheckoutPage() {
  const { t, l, lang } = useT();
  const navigate = useNavigate();
  const catalog = useCatalog((s) => s.catalog);
  const { lines, promoCode, clear } = useCart();
  const [draft, setDraft] = useState<Draft>(loadDraft);
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  useBackButton(true, '/cart');

  const pickupPointId = draft.pickupPointId || catalog?.pickupPoints[0]?.id || '';
  const update = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((d) => {
      const next = { ...d, [key]: value };
      try {
        sessionStorage.setItem(DRAFT_KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  // Server-side quote: the source of truth for the amount the user will pay.
  const itemsKey = JSON.stringify(toCartItems(lines));
  useEffect(() => {
    if (lines.length === 0) return;
    let cancelled = false;
    api
      .quote({
        items: JSON.parse(itemsKey),
        deliveryMethod: draft.delivery,
        promoCode: promoCode || null,
      })
      .then((q) => !cancelled && setQuote(q))
      .catch((e: unknown) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [itemsKey, draft.delivery, promoCode, lines.length]);

  const errors = {
    address: draft.delivery === 'courier' && !draft.address.trim() ? t('required') : null,
    name: !draft.name.trim() ? t('required') : null,
    phone: !PHONE.test(draft.phone.replace(/[\s\-()]/g, ''))
      ? draft.phone
        ? t('badPhone')
        : t('required')
      : null,
  };
  const valid = !errors.address && !errors.name && !errors.phone;

  const submit = async () => {
    setTouched(true);
    if (!valid) {
      haptic.notify('error');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const { order, invoiceUrl } = await api.createOrder({
        items: toCartItems(lines),
        deliveryMethod: draft.delivery,
        promoCode: quote?.promoError ? null : promoCode || null,
        customer: { name: draft.name, phone: draft.phone },
        address: draft.delivery === 'courier' ? draft.address : null,
        pickupPointId: draft.delivery === 'pickup' ? pickupPointId : null,
        deliverySlot: draft.slot,
        comment: draft.comment || null,
        paymentMethod: draft.payment,
      });
      clear();
      try {
        sessionStorage.removeItem(DRAFT_KEY);
      } catch {
        /* ignore */
      }
      let paid: string | null = null;
      if (order.status === 'awaiting_payment') paid = await api.payOrder(order, invoiceUrl);
      haptic.notify(paid === null || paid === 'paid' ? 'success' : 'warning');
      navigate(
        `/orders/${order.id}?placed=1${paid && paid !== 'paid' ? '&payment=cancelled' : ''}`,
        { replace: true },
      );
    } catch (e) {
      haptic.notify('error');
      setError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  };

  const payStars = draft.payment === 'stars';
  useMainButton(
    lines.length > 0
      ? {
          text:
            payStars && quote
              ? t('payStars', { stars: formatStars(quote.stars, lang) })
              : t('placeOrder'),
          hint: quote ? formatMoney(quote.total, lang) : undefined,
          progress: submitting,
          onClick: () => void submit(),
        }
      : null,
  );

  if (!catalog) return null;
  if (lines.length === 0 && !submitting) return <Navigate to="/cart" replace />;

  const field =
    'h-12 w-full rounded-xl bg-page px-3 text-[15px] outline-none focus:ring-2 focus:ring-button/40';
  const err = (msg: string | null) =>
    touched && msg ? <p className="mt-1 text-xs text-danger">{msg}</p> : null;

  return (
    <div className="space-y-3">
      <h1 className="px-1 text-2xl font-bold">{t('checkoutTitle')}</h1>

      <Section title={t('delivery')}>
        <Segmented
          name={t('delivery')}
          value={draft.delivery}
          onChange={(v) => {
            haptic.selection();
            update('delivery', v);
          }}
          options={[
            { value: 'courier', label: `🛵 ${t('courier')}` },
            { value: 'pickup', label: `🏪 ${t('pickup')}` },
          ]}
        />
        <div className="mt-3">
          {draft.delivery === 'courier' ? (
            <label className="block">
              <span className="mb-1 block text-sm text-hint">{t('address')}</span>
              <input
                className={field}
                value={draft.address}
                placeholder={t('addressPlaceholder')}
                onChange={(e) => update('address', e.target.value)}
                autoComplete="street-address"
                maxLength={200}
              />
              {err(errors.address)}
            </label>
          ) : (
            <fieldset className="space-y-2">
              <legend className="mb-1 text-sm text-hint">{t('pickupPoint')}</legend>
              {catalog.pickupPoints.map((p) => (
                <label
                  key={p.id}
                  className={clsx(
                    'flex cursor-pointer items-center gap-3 rounded-xl border-2 p-3',
                    p.id === pickupPointId
                      ? 'border-button bg-button/8'
                      : 'border-transparent bg-page',
                  )}
                >
                  <input
                    type="radio"
                    name="pickup"
                    className="accent-[var(--tg-button)]"
                    checked={p.id === pickupPointId}
                    onChange={() => {
                      haptic.selection();
                      update('pickupPointId', p.id);
                    }}
                  />
                  <span>
                    <span className="block font-semibold">{l(p.name)}</span>
                    <span className="block text-xs text-hint">{l(p.hours)}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
        </div>
        <label className="mt-3 block">
          <span className="mb-1 block text-sm text-hint">{t('slot')}</span>
          <select
            className={field}
            value={draft.slot}
            onChange={(e) => update('slot', e.target.value as DeliverySlot)}
          >
            {(['asap', 'morning', 'evening'] as const).map((s) => (
              <option key={s} value={s}>
                {t(`slot_${s}`)}
              </option>
            ))}
          </select>
        </label>
      </Section>

      <Section title={t('contacts')}>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-sm text-hint">{t('name')}</span>
            <input
              className={field}
              value={draft.name}
              onChange={(e) => update('name', e.target.value)}
              autoComplete="given-name"
              maxLength={64}
            />
            {err(errors.name)}
          </label>
          <label className="block">
            <span className="mb-1 block text-sm text-hint">{t('phone')}</span>
            <input
              className={field}
              value={draft.phone}
              onChange={(e) => update('phone', e.target.value)}
              inputMode="tel"
              autoComplete="tel"
              placeholder="+7 900 000-00-00"
              maxLength={20}
            />
            {err(errors.phone)}
          </label>
          <label className="block">
            <span className="mb-1 block text-sm text-hint">{t('comment')}</span>
            <textarea
              className={clsx(field, 'h-20 resize-none py-2')}
              value={draft.comment}
              onChange={(e) => update('comment', e.target.value)}
              maxLength={500}
            />
          </label>
        </div>
      </Section>

      <Section title={t('payment')}>
        <div className="grid gap-2">
          {(['stars', 'on_receipt'] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={draft.payment === m}
              onClick={() => {
                haptic.selection();
                update('payment', m);
              }}
              className={clsx(
                'pressable flex items-center gap-3 rounded-xl border-2 p-3 text-left',
                draft.payment === m ? 'border-button bg-button/8' : 'border-transparent bg-page',
              )}
            >
              <span className="text-2xl">{m === 'stars' ? '⭐' : '💳'}</span>
              <span>
                <span className="block font-semibold">{t(`pay_${m}`)}</span>
                <span className="block text-xs text-hint">{t(`pay_${m}_hint`)}</span>
              </span>
            </button>
          ))}
        </div>
      </Section>

      <Section>
        {quote ? (
          <Summary quote={quote} stars={payStars ? quote.stars : null} />
        ) : (
          <div className="h-24 animate-pulse rounded-xl bg-page" />
        )}
        {error && (
          <p className="mt-3 rounded-xl bg-danger/10 p-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </Section>
    </div>
  );
}
