"use client";

import { useState } from "react";
import Link from "next/link";
import { LogoMark } from "@/components/ui/logo";
import { Button } from "@/components/ui/button";
import { GlowCard } from "@/components/ui/spotlight-card";
import { authForgotPassword } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--bg-2)", border: "1px solid var(--glass-border)",
  borderRadius: 12, color: "var(--text)", fontSize: "0.9rem", padding: "11px 14px",
  fontFamily: "inherit", outline: "none", boxSizing: "border-box",
};

export default function ForgotPasswordPage() {
  const [email, setEmail]     = useState("");
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent]       = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authForgotPassword(email);
      setSent(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error de conexión");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "-15%", left: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.12), transparent 70%)", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", bottom: "-15%", right: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.08), transparent 70%)", filter: "blur(80px)" }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 360 }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <div style={{ display: "inline-flex", marginBottom: 12 }}><LogoMark size={40} /></div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>Recuperar contraseña</h1>
          <p style={{ color: "var(--text-3)", fontSize: "0.85rem", margin: "4px 0 0" }}>Te enviamos un enlace a tu correo</p>
        </div>

        {sent ? (
          <div style={{ textAlign: "center" }}>
            <div style={{ background: "rgba(48,209,88,0.08)", border: "1px solid rgba(48,209,88,0.2)", borderRadius: 12, padding: "14px 16px", color: "#34c759", fontSize: "0.9rem" }}>
              Si ese email tiene cuenta, te enviamos un enlace. Revisa tu correo (y el spam).
            </div>
            <Link href="/login" style={{ display: "block", marginTop: 16, color: "#4da3ff", fontSize: "0.85rem", textAlign: "center", textDecoration: "none" }}>
              Volver a iniciar sesión
            </Link>
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
                  <label style={{ color: "var(--text-3)", fontSize: "0.75rem", letterSpacing: "0.04em" }}>Email</label>
                  <input
                    type="email" value={email} onChange={e => setEmail(e.target.value)}
                    placeholder="tu@email.com" required autoFocus style={inputStyle}
                  />
                </div>
                <Button type="submit" disabled={loading} style={{ marginTop: 4, background: "#0071e3", color: "#fff", borderRadius: 12, fontSize: "0.95rem", padding: "12px", height: "auto", opacity: loading ? 0.7 : 1 }}>
                  {loading ? "Enviando..." : "Enviar enlace"}
                </Button>
              </form>
            </GlowCard>
            <Link href="/login" style={{ display: "block", marginTop: 18, color: "var(--text-3)", fontSize: "0.82rem", textAlign: "center", textDecoration: "none" }}>
              Volver a iniciar sesión
            </Link>
          </>
        )}
      </div>
    </div>
  );
}