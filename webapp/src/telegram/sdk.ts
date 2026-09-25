/**
 * Thin typed facade over `window.Telegram.WebApp`.
 *
 * Inside Telegram it drives the native MainButton / BackButton / haptics and themeParams.
 * In a regular browser (GitHub Pages demo) `isTelegram` is false and the UI renders
 * its own in-page equivalents, so every screen works the same way.
 */

type HapticImpact = 'light' | 'medium' | 'heavy' | 'rigid' | 'soft';
type HapticNotification = 'error' | 'success' | 'warning';

interface TgButton {
  setText(text: string): TgButton;
  setParams(p: {
    text?: string;
    color?: string;
    text_color?: string;
    is_active?: boolean;
    is_visible?: boolean;
    has_shine_effect?: boolean;
  }): TgButton;
  show(): TgButton;
  hide(): TgButton;
  enable(): TgButton;
  disable(): TgButton;
  showProgress(leaveActive?: boolean): TgButton;
  hideProgress(): TgButton;
  onClick(cb: () => void): TgButton;
  offClick(cb: () => void): TgButton;
}

interface TgBackButton {
  show(): void;
  hide(): void;
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
}

export interface ThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
  section_bg_color?: string;
  accent_text_color?: string;
  destructive_text_color?: string;
}

export interface TgWebApp {
  initData: string;
  initDataUnsafe: { user?: { id: number; first_name?: string; language_code?: string } };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  themeParams: ThemeParams;
  MainButton: TgButton;
  BackButton: TgBackButton;
  HapticFeedback: {
    impactOccurred(style: HapticImpact): void;
    notificationOccurred(type: HapticNotification): void;
    selectionChanged(): void;
  };
  ready(): void;
  expand(): void;
  close(): void;
  sendData(data: string): void;
  openInvoice(
    url: string,
    cb?: (status: 'paid' | 'cancelled' | 'failed' | 'pending') => void,
  ): void;
  isVersionAtLeast(v: string): boolean;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  enableClosingConfirmation?(): void;
  disableClosingConfirmation?(): void;
  onEvent(event: 'themeChanged', cb: () => void): void;
  offEvent(event: 'themeChanged', cb: () => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TgWebApp };
  }
}

export function getWebApp(): TgWebApp | undefined {
  return typeof window === 'undefined' ? undefined : window.Telegram?.WebApp;
}

/** True only when opened from a Telegram client (the SDK reports signed initData). */
export function isTelegram(): boolean {
  return Boolean(getWebApp()?.initData);
}

export function supports(version: string): boolean {
  const wa = getWebApp();
  return Boolean(wa && isTelegram() && wa.isVersionAtLeast(version));
}

export const haptic = {
  impact(style: HapticImpact = 'light') {
    if (supports('6.1')) getWebApp()?.HapticFeedback.impactOccurred(style);
    // Browsers only allow vibration after a real user gesture; skip it otherwise.
    else if (navigator.userActivation?.hasBeenActive) navigator.vibrate?.(8);
  },
  notify(type: HapticNotification) {
    if (supports('6.1')) getWebApp()?.HapticFeedback.notificationOccurred(type);
  },
  selection() {
    if (supports('6.1')) getWebApp()?.HapticFeedback.selectionChanged();
  },
};

const THEME_VARS: Record<keyof ThemeParams, string> = {
  bg_color: '--tg-bg',
  text_color: '--tg-text',
  hint_color: '--tg-hint',
  link_color: '--tg-link',
  button_color: '--tg-button',
  button_text_color: '--tg-button-text',
  secondary_bg_color: '--tg-secondary-bg',
  section_bg_color: '--tg-section-bg',
  accent_text_color: '--tg-accent',
  destructive_text_color: '--tg-destructive',
};

/** Copies Telegram themeParams into CSS variables consumed by Tailwind tokens. */
export function applyTheme(): void {
  const wa = getWebApp();
  const root = document.documentElement;
  if (!wa || !isTelegram()) return;
  root.dataset.tg = 'true';
  root.dataset.scheme = wa.colorScheme;
  for (const [key, cssVar] of Object.entries(THEME_VARS)) {
    const value = wa.themeParams[key as keyof ThemeParams];
    if (value) root.style.setProperty(cssVar, value);
  }
}

export function initTelegram(): void {
  const wa = getWebApp();
  if (!wa || !isTelegram()) return;
  wa.ready();
  wa.expand();
  applyTheme();
  wa.onEvent('themeChanged', applyTheme);
  if (wa.themeParams.secondary_bg_color && supports('6.1')) {
    wa.setHeaderColor?.(wa.themeParams.secondary_bg_color);
    wa.setBackgroundColor?.(wa.themeParams.secondary_bg_color);
  }
}

export function telegramLanguage(): string | undefined {
  return getWebApp()?.initDataUnsafe.user?.language_code;
}
