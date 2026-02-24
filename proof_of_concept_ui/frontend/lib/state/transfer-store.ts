import { create } from "zustand";

type TransferState = {
  queuedIds: string[];
  enqueue: (id: string) => void;
};

export const useTransferStore = create<TransferState>((set) => ({
  queuedIds: [],
  enqueue: (id) => set((state) => ({ queuedIds: [...state.queuedIds, id] }))
}));
