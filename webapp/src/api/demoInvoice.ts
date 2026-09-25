import { create } from 'zustand';
import type { PaymentResult } from './types';

interface DemoInvoiceState {
  invoice: { title: string; stars: number; resolve: (r: PaymentResult) => void } | null;
  open(title: string, stars: number): Promise<PaymentResult>;
  settle(result: PaymentResult): void;
}

/** In-page stand-in for Telegram's native Stars invoice sheet (demo mode only). */
export const useDemoInvoice = create<DemoInvoiceState>((set, get) => ({
  invoice: null,
  open: (title, stars) =>
    new Promise<PaymentResult>((resolve) => set({ invoice: { title, stars, resolve } })),
  settle: (result) => {
    get().invoice?.resolve(result);
    set({ invoice: null });
  },
}));
