"use client";
import { useAuthState } from "@/components/providers/auth-context";

// Centraliza el criterio de "¿la sesión activa es la cuenta demo?" -- mismo
// mecanismo de sesión que ya usa authMe()/AuthProvider, nada nuevo. Usar en
// cualquier componente que dispare una mutación (POST/PUT/DELETE) para
// deshabilitar el control correspondiente.
export function useIsDemo(): boolean {
  return useAuthState().username === "demo";
}

export const MENSAJE_DEMO = "No disponible en modo demo";
