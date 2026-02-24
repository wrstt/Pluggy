import { create } from "zustand";

type ProviderState = {
  selectedProviderIds: string[];
  toggleProvider: (id: string) => void;
};

export const useProviderStore = create<ProviderState>((set) => ({
  selectedProviderIds: [],
  toggleProvider: (id) =>
    set((state) => ({
      selectedProviderIds: state.selectedProviderIds.includes(id)
        ? state.selectedProviderIds.filter((value) => value !== id)
        : [...state.selectedProviderIds, id]
    }))
}));
