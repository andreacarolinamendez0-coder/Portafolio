"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { GlassPanel } from "@/components/ui/glass-panel";
import { LogoMark } from "@/components/ui/logo";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { useAtomSend } from "@/components/providers/atom-chat-context";

// Presencia global de Atom: burbuja fija + panel de chat superpuesto, sin
// navegar fuera de la pantalla actual. Comparte historial con bot/page.tsx
// via useAtomSend -- es la MISMA conversación, no una copia aparte.
export function AsistenteFlotante({ archivo }: { archivo: string }) {
  const { msgs, loading, send: enviar } = useAtomSend(archivo);
  const [abierto, setAbierto] = useState(false);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (abierto) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, loading, abierto]);

  function send() {
    if (!input.trim() || loading) return;
    const texto = input;
    setInput("");
    enviar(texto);
  }

  return (
    <div style={{ position: "fixed", bottom: 20, right: 20, zIndex: 60, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 12 }}>
      {abierto && (
        <GlassPanel
          style={{
            padding: 0, marginBottom: 0, width: 360, maxWidth: "calc(100vw - 40px)",
            height: 480, maxHeight: "calc(100vh - 120px)",
            display: "flex", flexDirection: "column", overflow: "hidden",
            boxShadow: "0 12px 40px rgba(0,0,0,0.4)",
          }}
        >
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--glass-border)", display: "flex", alignItems: "center", gap: 8 }}>
            <LogoMark size={20} />
            <span style={{ fontSize: 13, fontWeight: 600, flex: 1 }}>Atom</span>
            <Link href={`/portafolio/${archivo}/bot`} style={{ fontSize: 11, color: "var(--text-3)", textDecoration: "none" }} onClick={() => setAbierto(false)}>
              Pantalla completa
            </Link>
            <button
              onClick={() => setAbierto(false)}
              aria-label="Cerrar chat de Atom"
              style={{ background: "none", border: "none", color: "var(--text-3)", cursor: "pointer", fontSize: 14, lineHeight: 1, padding: 2 }}
            >
              ✕
            </button>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
            {msgs.length === 0 && (
              <p style={{ fontSize: 12.5, color: "var(--text-3)", textAlign: "center", margin: "40px 0" }}>
                Pregúntame sobre tu portafolio, mercados o estrategias de inversión.
              </p>
            )}
            {msgs.map((m, i) => (
              <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
                <div style={{
                  maxWidth: "85%", padding: "9px 13px",
                  borderRadius: m.role === "user" ? "14px 14px 3px 14px" : "14px 14px 14px 3px",
                  background: m.role === "user" ? "#0071e3" : "var(--glass)",
                  border: m.role === "bot" ? "1px solid rgba(255,255,255,0.08)" : "none",
                  color: m.role === "user" ? "#fff" : "var(--text)",
                  fontSize: "0.82rem", lineHeight: 1.5, whiteSpace: "pre-wrap",
                }}>
                  {m.text}
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ display: "flex" }}>
                <div style={{ padding: "9px 13px", borderRadius: "14px 14px 14px 3px", background: "var(--glass)", border: "1px solid rgba(255,255,255,0.08)", color: "var(--text-3)", fontSize: "0.8rem" }}>
                  Pensando...
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div style={{ padding: 10, borderTop: "1px solid var(--glass-border)" }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 12, padding: "4px 4px 4px 12px" }}>
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
                placeholder="Escribe tu pregunta..."
                disabled={loading}
                style={{ flex: 1, background: "none", border: "none", outline: "none", color: "var(--text)", fontSize: "0.82rem", fontFamily: "inherit", minWidth: 0 }}
              />
              <LiquidButton onClick={send} disabled={loading || !input.trim()} className="text-white font-semibold !px-4 !py-1.5 !text-xs">Enviar</LiquidButton>
            </div>
          </div>
        </GlassPanel>
      )}

      <button
        onClick={() => setAbierto(a => !a)}
        aria-label={abierto ? "Cerrar chat de Atom" : "Abrir chat de Atom"}
        style={{
          width: 52, height: 52, borderRadius: "50%", padding: 0, cursor: "pointer",
          background: "#0a0a0a", border: "1px solid rgba(255,255,255,0.14)",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: abierto ? "0 0 0 3px rgba(0,113,227,0.25)" : "0 6px 22px -6px rgba(0,113,227,0.45)",
        }}
      >
        <LogoMark size={30} />
      </button>
    </div>
  );
}
