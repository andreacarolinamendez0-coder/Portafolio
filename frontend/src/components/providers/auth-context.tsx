"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { authMe } from "@/lib/api";

interface AuthState {
  username: string | null;
  esAdmin: boolean;
  cargado: boolean;
}

const AuthContext = createContext<AuthState>({ username: null, esAdmin: false, cargado: false });

// Fuente única de la sesión activa para todo lo que cuelga de
// /portafolio/[archivo] -- un solo fetch a /api/auth/me compartido por
// todos los consumidores (el banner de demo, useIsDemo, el link de Admin,
// etc.) en vez de que cada componente pida lo mismo por su cuenta.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ username: null, esAdmin: false, cargado: false });

  useEffect(() => {
    authMe()
      .then(me => setState({ username: me.username, esAdmin: me.es_admin, cargado: true }))
      .catch(() => setState(s => ({ ...s, cargado: true })));
  }, []);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export function useAuthState() {
  return useContext(AuthContext);
}
