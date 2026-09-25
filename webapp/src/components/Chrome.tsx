import clsx from 'clsx';
import { AnimatePresence, motion } from 'motion/react';
import { formatStars } from '../domain/money';
import { Link, useLocation } from 'react-router';
import { api } from '../api';
import { useDemoInvoice } from '../api/demoInvoice';
import { useLang, useT } from '../i18n';
import { cartCount, useCart } from '../store/cart';
import { haptic, isTelegram } from '../telegram/sdk';
import { useMainButtonStore } from '../telegram/hooks';
import { Button } from './ui';

export function Header() {
  const { t, lang } = useT();
  const setLang = useLang((s) => s.setLang);
  const count = useCart((s) => cartCount(s.lines));
  const { pathname } = useLocation();
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-page/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-xl items-center gap-2 px-4">
        <Link to="/" className="flex min-w-0 items-center gap-2" aria-label="Zernolist">
          <img
            src={`${import.meta.env.BASE_URL}favicon.svg`}
            alt=""
            className="size-8 rounded-lg"
          />
          <div className="min-w-0 leading-tight">
            <div className="font-bold tracking-tight">Zernolist</div>
            <div className="truncate text-[11px] text-hint">{t('tagline')}</div>
          </div>
        </Link>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => setLang(lang === 'ru' ? 'en' : 'ru')}
            className="pressable h-9 rounded-full px-3 text-xs font-bold text-hint"
            aria-label="Switch language"
          >
            {lang === 'ru' ? 'EN' : 'RU'}
          </button>
          <NavIcon to="/orders" active={pathname.startsWith('/orders')} label={t('orders')}>
            <path d="M7 4h10a2 2 0 0 1 2 2v14l-3-2-2 2-2-2-2 2-2-2-3 2V6a2 2 0 0 1 2-2z M9 9h6 M9 13h4" />
          </NavIcon>
          <NavIcon to="/cart" active={pathname === '/cart'} label={t('cart')} badge={count}>
            <path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 8H6.2 M10 21h.01 M17 21h.01" />
          </NavIcon>
        </div>
      </div>
    </header>
  );
}

function NavIcon({
  to,
  active,
  label,
  badge,
  children,
}: {
  to: string;
  active: boolean;
  label: string;
  badge?: number;
  children: React.ReactNode;
}) {
  return (
    <Link
      to={to}
      aria-label={label}
      onClick={() => haptic.selection()}
      className={clsx(
        'pressable relative grid size-10 place-items-center rounded-full',
        active ? 'bg-button/12 text-accent' : 'text-fg',
      )}
    >
      <svg
        viewBox="0 0 24 24"
        className="size-6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {children}
      </svg>
      <AnimatePresence>
        {badge ? (
          <motion.span
            key={badge}
            initial={{ scale: 0.4 }}
            animate={{ scale: 1 }}
            exit={{ scale: 0 }}
            className="absolute -top-0.5 -right-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-button px-1 text-[11px] font-bold text-button-fg"
            data-testid="cart-badge"
          >
            {badge}
          </motion.span>
        ) : null}
      </AnimatePresence>
    </Link>
  );
}

export function Footer() {
  const { t } = useT();
  return (
    <footer className="mx-auto max-w-xl px-6 pt-6 pb-4 text-center text-[11px] leading-relaxed text-hint">
      <p>{t('demoNote')}</p>
      <p className="mt-1">
        Demo project / Демо-проект · API: <code>{api.mode}</code> ·{' '}
        <a
          className="text-link"
          href="https://github.com/sinnercode228/tg-shop-miniapp"
          target="_blank"
          rel="noreferrer"
        >
          GitHub
        </a>
      </p>
    </footer>
  );
}

/** In-page replacement for Telegram's MainButton when running in a normal browser. */
export function FallbackMainButton() {
  const button = useMainButtonStore((s) => s.button);
  if (isTelegram()) return null;
  return (
    <AnimatePresence>
      {button && (
        <motion.div
          initial={{ y: 80 }}
          animate={{ y: 0 }}
          exit={{ y: 80 }}
          transition={{ type: 'spring', stiffness: 420, damping: 36 }}
          className="fixed inset-x-0 bottom-0 z-30 bg-gradient-to-t from-page via-page/95 to-transparent px-4 pt-6 pb-[max(12px,env(safe-area-inset-bottom))]"
        >
          <button
            type="button"
            disabled={button.disabled || button.progress}
            onClick={() => {
              haptic.impact('medium');
              button.onClick();
            }}
            className="pressable mx-auto flex h-13 w-full max-w-xl items-center justify-center rounded-2xl bg-button text-[16px] font-semibold text-button-fg shadow-lg shadow-button/25 disabled:opacity-60"
            data-testid="main-button"
          >
            {button.progress ? (
              <span className="size-5 animate-spin rounded-full border-2 border-button-fg border-t-transparent" />
            ) : (
              button.text
            )}
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Demo stand-in for the native Telegram Stars invoice sheet. */
export function DemoInvoiceSheet() {
  const { t, lang } = useT();
  const invoice = useDemoInvoice((s) => s.invoice);
  const settle = useDemoInvoice((s) => s.settle);
  return (
    <AnimatePresence>
      {invoice && (
        <motion.div
          className="fixed inset-0 z-40 flex items-end bg-black/45"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => settle('cancelled')}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={t('demoInvoiceTitle')}
            initial={{ y: 300 }}
            animate={{ y: 0 }}
            exit={{ y: 300 }}
            transition={{ type: 'spring', stiffness: 380, damping: 34 }}
            onClick={(e) => e.stopPropagation()}
            className="mx-auto w-full max-w-xl rounded-t-3xl bg-section px-5 pt-3 pb-[max(20px,env(safe-area-inset-bottom))]"
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line" />
            <div className="flex items-center gap-3">
              <div className="grid size-14 place-items-center rounded-2xl bg-amber-400/20 text-3xl">
                ⭐
              </div>
              <div>
                <div className="font-semibold">{t('demoInvoiceTitle')}</div>
                <div className="text-sm text-hint">{invoice.title}</div>
              </div>
              <div className="ml-auto text-2xl font-bold tabular-nums">
                {formatStars(invoice.stars, lang)} ⭐
              </div>
            </div>
            <p className="mt-4 rounded-xl bg-page p-3 text-xs text-hint">{t('demoInvoiceHint')}</p>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <Button variant="soft" onClick={() => settle('cancelled')}>
                {t('cancel')}
              </Button>
              <Button
                onClick={() => {
                  haptic.notify('success');
                  settle('paid');
                }}
              >
                {t('confirmPay')}
              </Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
