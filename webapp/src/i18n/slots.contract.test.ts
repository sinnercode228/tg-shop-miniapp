import { renderHook } from '@testing-library/react';
import catalog from '../../../shared/catalog.json';
import type { DeliverySlot } from '../domain/types';
import { useLang, useT } from '.';

type TimedSlot = Exclude<DeliverySlot, 'asap'>;
const windows: Record<TimedSlot, string> = catalog.deliveryWindows;

describe('delivery slot contract (shared with pytest)', () => {
  for (const lang of ['ru', 'en'] as const) {
    for (const [slot, window] of Object.entries(windows) as [TimedSlot, string][]) {
      it(`${lang}: ${slot} label shows ${window}`, () => {
        useLang.setState({ lang });
        const { result } = renderHook(() => useT());
        expect(result.current.t(`slot_${slot}`)).toContain(window);
      });
    }
  }
});
