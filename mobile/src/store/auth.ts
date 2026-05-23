import { create } from "zustand";

interface AuthState {
  token: string | null;
  userId: string | null;
  workspaceId: string | null;
  setSession: (token: string, userId: string, workspaceId: string | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  userId: null,
  workspaceId: null,
  setSession: (token, userId, workspaceId) => set({ token, userId, workspaceId }),
  logout: () => set({ token: null, userId: null, workspaceId: null }),
}));
