"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LogoMark } from "@/components/ui/logo";
import { authMe, authLogout } from "@/lib/api";

interface Msg { role: "user" | "bot"; text: string }

export default function BotPage() {
  const router  = useRouter();
  const params  = useParams();
  const archivo = params.archivo as string;

  const [msgs, setMsgs]       = useState<Msg[]>([]);
  const [input, setInput]     = useState("");
  const [loading, setLoading] = useState(false);
  const [ready, setReady]     = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    authMe().then(me => {
      if (!me.authenticated) router.push("/login");
      else setReady(true);
    }).catch(() => router.push("/login"));
  }, [router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  async function send() {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMsgs(m => [...m, { role: "user", text: userMsg }]);
    setLoading(true);
    try {
      const historial = msgs.map(m => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));
      historial.push({ role: "user", content: userMsg });
      const res = await fetch(`/api/bot/${archivo}`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensaje: userMsg, historial }),
      });
      const data = await res.json();
      setMsgs(m => [...m, { role: "bot", text: data.respuesta ?? "Sin respuesta" }]);
    } catch {
      setMsgs(m => [...m, { role: "bot", text: "Error de conexión." }]);
    } finally {
      setLoading(false);
    }
  }

  if (!ready) return <div className="min-h-screen flex items-center justify-center" style={{ background: "#000", color: "#6e6e73", fontSize: 14 }}>Cargando...</div>;

  return (
    <div style={{ background: "#000", minHeight: "100vh", color: "#f5f5f7", display: "flex", flexDirection: "column" }}>
      <div style={{ maxWidth: 800, margin: "0 auto", padding: "24px 24px 0", width: "100%" }}>
        {/* Mini nav */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <LogoMark size={32} />
          <Link href={`/portafolio/${archivo}`} style={{ color: "#6e6e73", fontSize: 12, textDecoration: "none" }}>← Dashboard</Link>
          <span style={{ color: "#6e6e73", fontSize: 12 }}>/ Asistente IA</span>
          <button onClick={async () => { await authLogout(); router.push("/login"); }} style={{ marginLeft: "auto", background: "none", border: "none", color: "#6e6e73", fontSize: 12, cursor: "pointer" }}>Salir</button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 24px", maxWidth: 800, margin: "0 auto", width: "100%" }}>
        {msgs.length === 0 && (
          <div style={{ textAlign: "center", padding: "80px 0", color: "#6e6e73" }}>
            <LogoMark size={52} />
            <p style={{ marginTop: 16, fontSize: 14 }}>Pregúntame sobre tu portafolio, mercados o estrategias de inversión.</p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", marginBottom: 12 }}>
            <div style={{
              maxWidth: "80%", padding: "12px 16px", borderRadius: m.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
              background: m.role === "user" ? "#0071e3" : "rgba(255,255,255,0.06)",
              border: m.role === "bot" ? "1px solid rgba(255,255,255,0.08)" : "none",
              color: "#f5f5f7", fontSize: "0.9rem", lineHeight: 1.5,
              whiteSpace: "pre-wrap",
            }}>
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: "flex", marginBottom: 12 }}>
            <div style={{ padding: "12px 16px", borderRadius: "18px 18px 18px 4px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)", color: "#6e6e73", fontSize: "0.9rem" }}>
              Pensando...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "16px 24px 32px", maxWidth: 800, margin: "0 auto", width: "100%" }}>
        <div style={{ display: "flex", gap: 8, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 16, padding: "8px 8px 8px 16px", alignItems: "center" }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Escribe tu pregunta..."
            disabled={loading}
            style={{ flex: 1, background: "none", border: "none", outline: "none", color: "#f5f5f7", fontSize: "0.9rem", fontFamily: "inherit" }}
          />
          <Button onClick={send} disabled={loading || !input.trim()} style={{ background: "#0071e3", color: "#fff", borderRadius: 10, padding: "8px 16px", height: "auto" }}>
            Enviar
          </Button>
        </div>
      </div>
    </div>
  );
}
