"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { Button } from "@/components/ui/button";
import { GlowCard } from "@/components/ui/spotlight-card";
import { authResetPassword } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--bg-2)", border: "1px solid var(--glass-border)",
  borderRadius: 12, color: "var(--text)", fontSize: "0.9rem", padding: "11px 14px",
  fontFamily: "inherit", outline: "none", boxSizing: "border-box",
};

function ResetForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [done, setDone]         = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 6) { setError("La contraseña debe tener al menos 6 caracteres"); return; }
    setLoading(true);
    try {
      await authResetPassword(token, password);
      setDone(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error de conexión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ width: "100%", maxWidth: 360 }}>
      <div style={{ textAlign: "center", marginBottom: 24 }}>
        <div style={{ display: "inline-flex", marginBottom: 12 }}><LogoMark size={40} /></div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>Nueva contraseña</h1>
        <p style={{ color: "var(--text-3)", fontSize: "0.85rem", margin: "4px 0 0" }}>Mínimo 6 caracteres</p>
      </div>

      {done ? (
        <div style={{ textAlign: "center" }}>
          <div style={{ background: "rgba(48,209,88,0.08)", border: "1px solid rgba(48,209,88,0.2)", borderRadius: 12, padding: "14px 16px", color: "#34c759", fontSize: "0.9rem" }}>
            Tu contraseña fue actualizada.
          </div>
          <Link href="/login" style={{ display: "block", marginTop: 16, textAlign: "center", background: "#0071e3", color: "#fff", borderRadius: 12, fontSize: "0.95rem", padding: "12px", textDecoration: "none", fontWeight: 500 }}>
            Iniciar sesión
          </Link>
        </div>
      ) : !token ? (
        <div style={{ background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 12, padding: "12px 16px", color: "#ff6961", fontSize: "0.875rem", textAlign: "center" }}>
          Enlace inválido o incompleto. Solicita uno nuevo desde <Link href="/login" style={{ color: "#4da3ff" }}>iniciar sesión</Link>.
        </div>
      ) : (
        <>
          {error && (
            <div style={{ background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 12, padding: "12px 16px", marginBottom: 16, color: "#ff6961", fontSize: "0.875rem" }}>
              {error}
            </div>
          )}
          <GlowCard glowColor="blue">
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <label style={{ color: "var(--text-3)", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Nueva contraseña</label>
                <input
                  type="password" value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••" required autoFocus style={inputStyle}
                />
              </div>
              <Button type="submit" disabled={loading} style={{ marginTop: 4, background: "#0071e3", color: "#fff", borderRadius: 12, fontSize: "0.95rem", padding: "12px", height: "auto", opacity: loading ? 0.7 : 1 }}>
                {loading ? "Guardando..." : "Guardar contraseña"}
              </Button>
            </form>
          </GlowCard>
        </>
      )}
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "-15%", left: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.12), transparent 70%)", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", bottom: "-15%", right: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.08), transparent 70%)", filter: "blur(80px)" }} />
      </div>
      {/* Suspense obligatorio: useSearchParams sin él pasa en dev pero rompe el build */}
      <div style={{ position: "relative", zIndex: 1, width: "100%", display: "flex", justifyContent: "center" }}>
        <Suspense fallback={<div style={{ color: "var(--text-3)", fontSize: 14 }}>Cargando…</div>}>
          <ResetForm />
        </Suspense>
      </div>
    </div>
  );
}