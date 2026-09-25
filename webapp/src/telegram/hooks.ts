import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { create } from 'zustand';
import { getWebApp, isTelegram } from './sdk';

export interface MainButtonState {
  text: string;
  onClick: () => void;
  disabled?: boolean;
  progress?: boolean;
  /** Optional right-aligned hint shown by the in-page fallback button (e.g. the total). */
  hint?: string;
}

/** Holds the current main button so the browser fallback can render it. */
export const useMainButtonStore = create<{
  button: MainButtonState | null;
  set: (b: MainButtonState | null) => void;
}>((set) => ({ button: null, set: (button) => set({ button }) }));

/**
 * Declarative MainButton: native Telegram button inside the client,
 * a sticky in-page button (see `FallbackMainButton`) in the browser.
 */
export function useMainButton(state: MainButtonState | null): void {
  const setButton = useMainButtonStore((s) => s.set);
  const handler = useRef(state?.onClick);
  useEffect(() => {
    handler.current = state?.onClick;
  });

  const text = state ? (state.hint ? `${state.text} · ${state.hint}` : state.text) : null;
  const disabled = state?.disabled ?? false;
  const progress = state?.progress ?? false;
  const visible = state !== null;

  useEffect(() => {
    const wa = getWebApp();
    if (!visible) {
      setButton(null);
      if (wa && isTelegram()) wa.MainButton.hide();
      return;
    }
    const click = () => handler.current?.();
    if (wa && isTelegram()) {
      const mb = wa.MainButton;
      mb.setParams({ text: text ?? '', is_active: !disabled, is_visible: true });
      if (progress) mb.showProgress(false);
      else mb.hideProgress();
      mb.onClick(click);
      return () => {
        mb.offClick(click);
      };
    }
    setButton({ text: text ?? '', onClick: click, disabled, progress });
    return undefined;
  }, [visible, text, disabled, progress, setButton]);

  useEffect(
    () => () => {
      setButton(null);
      const wa = getWebApp();
      if (wa && isTelegram()) wa.MainButton.hide();
    },
    [setButton],
  );
}

/** Shows Telegram's BackButton (navigates back) while the calling screen is mounted. */
export function useBackButton(enabled = true, to?: string): void {
  const navigate = useNavigate();
  useEffect(() => {
    const wa = getWebApp();
    if (!enabled || !wa || !isTelegram()) return;
    const back = () => (to ? navigate(to) : navigate(-1));
    wa.BackButton.onClick(back);
    wa.BackButton.show();
    return () => {
      wa.BackButton.offClick(back);
      wa.BackButton.hide();
    };
  }, [enabled, navigate, to]);
}
