"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { authActivate } from "@/lib/api";

type Estado = "cargando" | "ok" | "error";

function Activar() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [estado, setEstado] = useState<Estado>("cargando");
  const [msg, setMsg]       = useState("");
  const corrio = useRef(false);

  useEffect(() => {
    if (corrio.current) return;   // evita doble POST (StrictMode)
    corrio.current = true;
    if (!token) { setEstado("error"); setMsg("Enlace de activación inválido o incompleto."); return; }
    authActivate(token)
      .then(() => { setEstado("ok"); setMsg("¡Cuenta activada! Ya puedes iniciar sesión."); })
      .catch((err: unknown) => { setEstado("error"); setMsg(err instanceof Error ? err.message : "No se pudo activar la cuenta."); });
  }, [token]);

  const color  = estado === "ok" ? "#34c759" : estado === "error" ? "#ff6961" : "var(--text-3)";
  const bg     = estado === "ok" ? "rgba(48,209,88,0.08)" : "rgba(255,69,58,0.08)";
  const border = estado === "ok" ? "rgba(48,209,88,0.2)"  : "rgba(255,69,58,0.2)";

  return (
    <div style={{ width: "100%", maxWidth: 360, textAlign: "center" }}>
      <div style={{ display: "inline-flex", marginBottom: 14 }}><LogoMark size={40} /></div>
      {estado === "cargando" ? (
        <p style={{ color: "var(--text-3)", fontSize: 14 }}>Activando tu cuenta…</p>
      ) : (
        <>
          <div style={{ background: bg, border: `1px solid ${border}`, borderRadius: 12, padding: "14px 16px", color, fontSize: "0.9rem" }}>
            {msg}
          </div>
          <Link href="/login" style={{ display: "block", marginTop: 16, background: "#0071e3", color: "#fff", borderRadius: 12, fontSize: "0.95rem", padding: "12px", textDecoration: "none", fontWeight: 500 }}>
            Ir a iniciar sesión
          </Link>
        </>
      )}
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