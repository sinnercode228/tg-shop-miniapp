import { create } from 'zustand';
import { api } from '../api';
import type { Catalog } from '../domain/types';

interface CatalogState {
  catalog: Catalog | null;
  error: string | null;
  loading: boolean;
  load(): Promise<void>;
}

export const useCatalog = create<CatalogState>((set, get) => ({
  catalog: null,
  error: null,
  loading: false,
  load: async () => {
    if (get().catalog || get().loading) return;
    set({ loading: true, error: null });
    try {
      set({ catalog: await api.getCatalog(), loading: false });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e), loading: false });
    }
  },
}));
