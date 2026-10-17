"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { auth } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  refresh: () => Promise<User | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refresh = useCallback(async (): Promise<User | null> => {
    try {
      const res = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (!res.ok) {
        setUser(null);
        return null;
      }
      const data = (await res.json()) as User;
      setUser(data);
      return data;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } catch {
      /* ignore */
    }
    setUser(null);
    router.replace("/login");
  }, [router]);

  const value = useMemo<AuthState>(
    () => ({ user, loading, setUser, refresh, logout }),
    [user, loading, refresh, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
