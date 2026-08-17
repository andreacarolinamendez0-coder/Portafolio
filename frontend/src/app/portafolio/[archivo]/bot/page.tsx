"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { LogoMark } from "@/components/ui/logo";
import { authMe } from "@/lib/api";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { PageIntro } from "@/components/ui/page-intro";
import { useAtomSend } from "@/components/providers/atom-chat-context";
import { useIsDemo, MENSAJE_DEMO } from "@/lib/useIsDemo";

export default function BotPage() {
  const router  = useRouter();
  const params  = useParams();
  const archivo = params.archivo as string;

  const { msgs, loading, send: enviar } = useAtomSend(archivo);
  const isDemo = useIsDemo();
  const [input, setInput]     = useState("");
  const [ready, setReady]     = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    authMe().then(me => {
      if (!me.authenticated) router.push("/login");
      else setReady(true);
    }).catch(() => router.push("/login"));
  }, [router]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, loading]);

  function send() {
    if (!input.trim() || loading) return;
    const texto = input;
    setInput("");
    enviar(texto);
  }

  if (!ready) return <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)", color: "var(--text-3)", fontSize: 14 }}>Cargando...</div>;

  return (
    <>
      <style>{`
        @keyframes typing { 0%,60%,100% { opacity: 0.25; } 30% { opacity: 1; } }
        .typing-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); display: inline-block; animation: typing 1.2s infinite; }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes logoGlow { 0%,100% { filter: drop-shadow(0 0 14px rgba(0,113,227,0.25)); } 50% { filter: drop-shadow(0 0 26px rgba(0,113,227,0.45)); } }
      `}</style>

       <PageIntro
                       archivo={archivo}
                       texto="Este es el chat con Atom. Pregúntale sobre tu portafolio, los mercados o cualquier estrategia de inversión. Recuerda que Atom es un asistente virtual y no constituye asesoramiento financiero. Sus respuestas se basan en datos históricos y no garantizan resultados futuros."
                     />

      {/* Mensajes */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 24px", maxWidth: 800, margin: "0 auto", width: "100%" }}>
        {msgs.length === 0 && (
          <div style={{ textAlign: "center", padding: "80px 0", color: "var(--text-3)" }}>
            <div style={{ animation: "logoGlow 3s ease-in-out infinite", display: "inline-block" }}>
              <LogoMark size={52} />
            </div>
            <p style={{ marginTop: 20, fontSize: 15, color: "var(--text-2)" }}>¿En qué te ayudo hoy?</p>
            <p style={{ marginTop: 6, fontSize: 13 }}>
              {isDemo ? "En modo demo, Atom es de solo lectura — no se pueden iniciar conversaciones nuevas." : "Pregúntame sobre tu portafolio, mercados o estrategias de inversión."}
            </p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", marginBottom: 12 }}>
            <div style={{
              maxWidth: "80%", padding: "12px 16px",
              borderRadius: m.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
              background: m.role === "user" ? "#0071e3" : "var(--glass)",
              border: m.role === "bot" ? "1px solid rgba(255,255,255,0.08)" : "none",
              boxShadow: m.role === "user" ? "0 4px 16px -6px rgba(0,113,227,0.5)" : "none",
              color: m.role === "user" ? "#fff" : "#f5f5f7",
              fontSize: "0.9rem", lineHeight: 1.55, whiteSpace: "pre-wrap",
            }}>
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: "flex", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "14px 18px", borderRadius: "18px 18px 18px 4px", background: "var(--glass)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "16px 24px 32px", maxWidth: 800, margin: "0 auto", width: "100%" }}>
        <div style={{ display: "flex", gap: 8, background: "var(--glass)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 16, padding: "8px 8px 8px 16px", alignItems: "center", backdropFilter: "blur(12px)" }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
            placeholder={isDemo ? MENSAJE_DEMO : "Escribe tu pregunta..."}
            disabled={loading || isDemo}
            style={{ flex: 1, background: "none", border: "none", outline: "none", color: "var(--text)", fontSize: "0.9rem", fontFamily: "inherit" }}
          />
          <LiquidButton onClick={send} disabled={loading || isDemo || !input.trim()} title={isDemo ? MENSAJE_DEMO : undefined} className="text-white font-semibold !px-6 !py-2.5">Enviar</LiquidButton>
        </div>
      </div>
    </>
  );
}
