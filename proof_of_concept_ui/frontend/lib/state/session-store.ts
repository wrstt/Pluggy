import { create } from "zustand";

type SessionState = {
  rdConnected: boolean;
  setRdConnected: (value: boolean) => void;
};

export const useSessionStore = create<SessionState>((set) => ({
  rdConnected: false,
  setRdConnected: (value) => set({ rdConnected: value })
}));
