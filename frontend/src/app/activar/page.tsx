"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { Button } from "@/components/ui/button";
import { GlowCard } from "@/components/ui/spotlight-card";
import { authVerifyPin, authResendPin } from "@/lib/api";
import { ApiError } from "@/lib/api";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--bg-2)", border: "1px solid var(--glass-border)",
  borderRadius: 12, color: "var(--text)", fontSize: "1.4rem", letterSpacing: "0.4em",
  textAlign: "center", padding: "12px 14px", fontFamily: "inherit", outline: "none", boxSizing: "border-box",
};
const TOTAL = 10 * 60;

function Activar() {
  const params = useSearchParams();
  const router = useRouter();
  const email = params.get("email") ?? "";
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reenviando, setReenviando] = useState(false);
  const [bloqueado, setBloqueado] = useState(false);

  const KEY = email ? `pin_expira_${email}` : "";
  const [expiraMs, setExpiraMs] = useState<number | null>(null);
  const [segundos, setSegundos] = useState<number | null>(null);

  // Inicializa el vencimiento SOLO en cliente (nada de Date.now/localStorage en el render)
  useEffect(() => {
    if (!KEY) return;
    const guardado = localStorage.getItem(KEY);
    const ms = guardado ? Number(guardado) : Date.now() + TOTAL * 1000;
    if (!guardado) localStorage.setItem(KEY, String(ms));
    setExpiraMs(ms);
  }, [KEY]);

  // Countdown desde el timestamp absoluto
  useEffect(() => {
    if (expiraMs == null) return;
    const tick = () => setSegundos(Math.max(0, Math.round((expiraMs - Date.now()) / 1000)));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [expiraMs]);

  const muerto = bloqueado || (segundos !== null && segundos <= 0);
  const mmss = segundos == null ? "" :
    `${String(Math.floor(segundos / 60)).padStart(2, "0")}:${String(segundos % 60).padStart(2, "0")}`;

  async function verificar(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await authVerifyPin(email, pin.trim());
      if (KEY) localStorage.removeItem(KEY);
      router.push("/");   // el server ya abrió sesión (auto-login)
    } catch (err: unknown) {
      if (err instanceof ApiError && err.data?.bloqueado) setBloqueado(true);
      setError(err instanceof Error ? err.message : "Error de conexión");
    } finally { setLoading(false); }
  }

  async function reenviar() {
    setError(""); setReenviando(true);
    try {
      await authResendPin(email);
      const nuevo = Date.now() + TOTAL * 1000;
      if (KEY) localStorage.setItem(KEY, String(nuevo));
      setExpiraMs(nuevo);
      setPin(""); setBloqueado(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "No se pudo reenviar");
    } finally { setReenviando(false); }
  }

  if (!email) {
    return (
      <div style={{ width: "100%", maxWidth: 360, textAlign: "center" }}>
        <div style={{ display: "inline-flex", marginBottom: 14 }}><LogoMark size={40} /></div>
        <p style={{ color: "var(--text-3)", fontSize: "0.9rem" }}>
          Falta el correo. <Link href="/register" style={{ color: "#4da3ff" }}>Regístrate</Link> o{" "}
          <Link href="/login" style={{ color: "#4da3ff" }}>inicia sesión</Link> de nuevo.
        </p>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", maxWidth: 360 }}>
      <div style={{ textAlign: "center", marginBottom: 24 }}>
        <div style={{ display: "inline-flex", marginBottom: 12 }}><LogoMark size={40} /></div>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>Activa tu cuenta</h1>
        <p style={{ color: "var(--text-3)", fontSize: "0.85rem", margin: "4px 0 0" }}>
          Te enviamos un código a <strong style={{ color: "var(--text-2)" }}>{email}</strong>
        </p>
      </div>

      {error && (
        <div style={{ background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.2)", borderRadius: 12, padding: "12px 16px", marginBottom: 16, color: "#ff6961", fontSize: "0.875rem" }}>
          {error}
        </div>
      )}

      <GlowCard glowColor="blue">
        <form onSubmit={verificar} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <input
            value={pin}
            onChange={e => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="••••••" inputMode="numeric" autoFocus required style={inputStyle}
          />
          <div style={{ textAlign: "center", fontSize: "0.8rem", color: muerto ? "#ff6961" : "var(--text-3)" }}>
            {segundos === null
              ? "\u00A0"
              : muerto
              ? "Este código ya no sirve, pide uno nuevo"
              : `El código vence en ${mmss}`}
          </div>
          <Button type="submit" disabled={loading || pin.length < 6 || muerto} style={{ background: "#0071e3", color: "#fff", borderRadius: 12, fontSize: "0.95rem", padding: "12px", height: "auto", opacity: (loading || pin.length < 6 || muerto) ? 0.6 : 1 }}>
            {loading ? "Verificando..." : "Activar y entrar"}
          </Button>
        </form>
      </GlowCard>

      <button
        onClick={reenviar}
        disabled={reenviando}
        style={{ display: "block", width: "100%", marginTop: 16, background: "none", border: "none", color: "#4da3ff", fontSize: "0.82rem", cursor: reenviando ? "default" : "pointer", fontFamily: "inherit" }}
      >
        {reenviando ? "Enviando..." : "Reenviar código"}
      </button>
    </div>
  );
}

export default function ActivarPage() {
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "-15%", left: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.12), transparent 70%)", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", bottom: "-15%", right: "-10%", width: 600, height: 600, background: "radial-gradient(circle, rgba(0,113,227,0.08), transparent 70%)", filter: "blur(80px)" }} />
      </div>
      <div style={{ position: "relative", zIndex: 1, width: "100%", display: "flex", justifyContent: "center" }}>
        <Suspense fallback={<div style={{ color: "var(--text-3)", fontSize: 14 }}>Cargando…</div>}>
          <Activar />
        </Suspense>
      </div>
    </div>
  );
}