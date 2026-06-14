import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiFetch, setStoredToken } from "../api/client";
import type { User } from "../api/types";

type AuthContextValue = {
  user: User | null;
  bootstrapped: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => void;
  refreshMe: () => Promise<User | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [bootstrapped, setBootstrapped] = useState(false);

  async function refreshMe() {
    try {
      const currentUser = await apiFetch<User>("/api/auth/me");
      setUser(currentUser);
      return currentUser;
    } catch {
      setStoredToken(null);
      setUser(null);
      return null;
    } finally {
      setBootstrapped(true);
    }
  }

  async function login(username: string, password: string) {
    const token = await apiFetch<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setStoredToken(token.access_token);
    const currentUser = await apiFetch<User>("/api/auth/me");
    setUser(currentUser);
    return currentUser;
  }

  function logout() {
    setStoredToken(null);
    setUser(null);
  }

  useEffect(() => {
    refreshMe();
  }, []);

  const value = useMemo(
    () => ({ user, bootstrapped, login, logout, refreshMe }),
    [user, bootstrapped],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
