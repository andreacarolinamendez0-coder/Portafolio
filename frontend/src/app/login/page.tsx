"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authLogin } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authLogin(email, password);
      router.push("/portafolios");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error de conexión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6" style={{ background: "#000" }}>
      <div className="w-full max-w-sm">

        {/* Header */}
        <div className="flex flex-col items-center mb-8 gap-3">
          <LogoMark size={48} />
          <div className="text-center">
            <h1 style={{ color: "#f5f5f7", fontSize: "1.3rem", fontWeight: 600, letterSpacing: "-0.02em", marginBottom: 4 }}>
              Sistema de Portafolio
            </h1>
            <p style={{ color: "#6e6e73", fontSize: "0.82rem" }}>Ingresa con tu cuenta</p>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)",
            borderRadius: 12, padding: "12px 16px", marginBottom: 16,
            color: "#ff6961", fontSize: "0.875rem",
          }}>
            {error}
          </div>
        )}

        {/* Card */}
        <div style={{
          background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 18, padding: 22, backdropFilter: "blur(20px)",
        }}>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>
                Email
              </Label>
              <Input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="tu@email.com"
                required
                autoFocus
                style={{
                  background: "#111", border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 12, color: "#f5f5f7", fontSize: "0.9rem",
                }}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label style={{ color: "#6e6e73", fontSize: "0.75rem", letterSpacing: "0.04em" }}>
                Contraseña
              </Label>
              <Input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                style={{
                  background: "#111", border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 12, color: "#f5f5f7", fontSize: "0.9rem",
                }}
              />
            </div>
            <Button
              type="submit"
              disabled={loading}
              style={{
                marginTop: 4, background: "#0071e3", color: "#fff", borderRadius: 12,
                fontSize: "0.95rem", padding: "12px", height: "auto",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? "Entrando..." : "Entrar"}
            </Button>
          </form>
        </div>

        <p className="text-center mt-5" style={{ color: "#6e6e73", fontSize: "0.78rem" }}>
          ¿No tienes cuenta?{" "}
          <Link href="/register" style={{ color: "#4da3ff", textDecoration: "none" }}>
            Regístrate
          </Link>
        </p>
      </div>
    </div>
  );
}
