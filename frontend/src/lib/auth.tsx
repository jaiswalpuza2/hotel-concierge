"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, refreshAccessToken, setAccessToken } from "./api";

export interface AuthUser {
  id: string;
  email: string;
  role: "admin" | "staff";
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function decodeUser(token: string): AuthUser | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(json) as { sub?: string; role?: "admin" | "staff"; email?: string };
    if (!payload.sub || !payload.role) return null;
    return { id: payload.sub, email: payload.email ?? "", role: payload.role };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore the session from the HttpOnly refresh cookie on first load.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const token = await refreshAccessToken();
      if (!cancelled) {
        setUser(token ? decodeUser(token) : null);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      credentials: "include",
    });
    const data = (await res.json().catch(() => ({}))) as {
      access_token?: string;
      user?: AuthUser;
      error?: { message?: string };
    };
    if (!res.ok || !data.access_token || !data.user) {
      throw new Error(data.error?.message ?? "Sign-in failed");
    }
    setAccessToken(data.access_token);
    setUser(data.user);
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" }).catch(() => null);
    setAccessToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Re-export so pages can call the API without importing two modules. */
export { api };
