"use client";
import { useEffect, useState, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { getDashboard, type DashboardData } from "@/lib/api";
import { GlassBackground } from "@/components/ui/glass-background";
import { GlassPanel } from "@/components/ui/glass-panel";
import { GlowPanel } from "@/components/ui/glow-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { PropuestaEditor, type Propuesta } from "@/components/ui/propuesta-editor";
import { PageIntro } from "@/components/ui/page-intro";

interface Msg { role: "user" | "assistant"; content: string }

export default function AnalistaPage() {
  const params  = useParams();
  const router  = useRouter();
  const searchParams = useSearchParams();
  const archivo = params.archivo as string;

  const [data, setData]       = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  const [msgs, setMsgs]       = useState<Msg[]>([]);
  const [input, setInput]     = useState("");
  const [enviando, setEnviando] = useState(false);
  const [propuesta, setPropuesta] = useState<Propuesta | null>(null);
  const [aplicando, setAplicando] = useState(false);
  const [msgEstado, setMsgEstado] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const [destinoSeguimiento, setDestinoSeguimiento] = useState<string | null>(null);
  // "rebalanceo" cuando se llega desde el aviso flotante de Seguimiento --
  // se reenvía en cada llamada para que el Analista siempre tenga el
  // contexto real (recalculado server-side, nunca confía en lo que mande
  // el cliente). Ver dashboard.py:_sistema_analista.
  const [motivo] = useState<string | null>(searchParams.get("motivo"));

  useEffect(() => {
    getDashboard(archivo)
      .then(d => {
        setData(d);
        if (motivo === "rebalanceo") {
          const primero: Msg = { role: "user", content: "Vengo desde Seguimiento: mi portafolio se desvió de la meta." };
          setMsgs([primero]);
          enviarHistorial([primero]);
        } else {
          setMsgs([{ role: "assistant", content: `Hola ${d.portafolio?.nombre ? "" : ""}👋 Soy tu analista. Te ayudo a construir una propuesta de inversión personalizada o a ajustar tu portafolio. Para empezar, cuéntame: ¿qué te gustaría lograr con esta inversión?` }]);
        }
      })
      .catch(() => router.push("/login"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [archivo, router]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, propuesta]);

  async function enviarHistorial(nuevos: Msg[]) {
    setEnviando(true);
    try {
      const r = await fetch(`/api/analista-chat/${archivo}`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          historial: nuevos.map(m => ({ role: m.role, content: m.content })),
          ...(motivo ? { motivo } : {}),
        }),
      });
      const d = await r.json();
      const resp: string = d.respuesta ?? "Sin respuesta";

      // ¿La respuesta es el JSON de propuesta?
      const json = extraerJSON(resp);
      if (json && json.accion === "analizar") {
        // Pedir la composición real al backend
        await generarPropuesta(json);
      } else {
        setMsgs(m => [...m, { role: "assistant", content: resp }]);
      }
    } catch {
      setMsgs(m => [...m, { role: "assistant", content: "Error de conexión. Intenta de nuevo." }]);
    } finally {
      setEnviando(false);
    }
  }

  async function enviar() {
    const texto = input.trim();
    if (!texto || enviando) return;
    setInput("");
    const nuevos: Msg[] = [...msgs, { role: "user", content: texto }];
    setMsgs(nuevos);
    await enviarHistorial(nuevos);
  }

  async function generarPropuesta(json: Record<string, unknown>) {
    setMsgs(m => [...m, { role: "assistant", content: "Perfecto, déjame calcular la composición óptima para ti..." }]);
    try {
      const r = await fetch(`/api/generar-propuesta/${archivo}`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(json),
      });
      const d = await r.json();
      if (d.ok && d.propuesta) {
        setPropuesta(d.propuesta as Propuesta);
        const composicionReal = Object.entries(d.propuesta.pesos)
          .map(([k, v]) => `${k}: ${((v as number) * 100).toFixed(1)}%`)
          .join(", ");
        setMsgs(m => [...m, {
          role: "assistant",
          content: `Propuesta generada — composición real: ${composicionReal}. Inversión: ${d.propuesta.inversion} COP. DCA: ${d.propuesta.aporte_dca} COP cada ${d.propuesta.frecuencia_meses} mes(es). Horizonte: ${d.propuesta.horizonte} años. ¿Quieres ajustar algo?`,
        }]);
      } else {
        setMsgs(m => [...m, { role: "assistant", content: `No pude generar la propuesta: ${d.error ?? "error desconocido"}` }]);
      }
    } catch {
      setMsgs(m => [...m, { role: "assistant", content: "Error al generar la propuesta." }]);
    }
  }

  async function aplicar(tipo: "reemplazar" | "nuevo", pesosEditados: Record<string, number>) {
    if (!propuesta) return;
    setAplicando(true);
    setMsgEstado("");
    try {
      const r = await fetch(`/api/aplicar-propuesta/${archivo}`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...propuesta, pesos: pesosEditados, tipo }),
      });
      const d = await r.json();
      if (d.ok) {
        const destino = d.redirigir?.replace("/seguimiento/", "") ?? archivo;
        setPropuesta(null);
        setMsgs(m => [...m, {
          role: "assistant",
          content: `Listo. ${d.mensaje ?? "Tu portafolio fue actualizado."} Cuando quieras, puedes ir a Seguimiento para registrar tus compras — o seguir aquí si deseas ajustar algo más.`,
        }]);
        setDestinoSeguimiento(destino);
      } else {
        setMsgEstado(`Error: ${d.error ?? "no se pudo aplicar"}`);
      }
    } catch {
      setMsgEstado("Error de conexión al aplicar.");
    } finally {
      setAplicando(false);
    }
  }

  if (loading) return <div style={s.load}>Cargando...</div>;
  if (!data)   return <div style={s.load}>No se pudo cargar</div>;

  const tieneInv = (data.tiempo_real?.posiciones?.length ?? 0) > 0;

  return (
    <>
    
        <h2 style={{ fontSize: "1.4rem", margin: "16px 0 24px" }}>Analista — {data.portafolio.nombre}</h2>
         <PageIntro
               archivo={archivo}
               texto="Atom estudia tu perfil y arma una propuesta de portafolio. Puedes simular escenarios y ajustar los pesos antes de aplicarla. Recuerda que Atom es un asistente virtual y no constituye asesoramiento financiero. Sus respuestas se basan en datos históricos y no garantizan resultados futuros."
             /> 
        {/* Chat */}
        <GlassPanel style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--glass-border)", display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#30d158" }} />
            <span style={{ fontSize: 13, fontWeight: 600 }}>Analista IA</span>
          </div>

          <div style={{ height: 420, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
            {msgs.map((m, i) => (
              <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
                <div style={{
                  maxWidth: "82%", padding: "11px 15px",
                  borderRadius: m.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                  background: m.role === "user" ? "#0071e3" : "var(--glass)",
                  border: m.role === "assistant" ? "1px solid var(--glass-border)" : "none",
                  color: m.role === "user" ? "#fff" : "var(--text)",
                  fontSize: "0.9rem", lineHeight: 1.55, whiteSpace: "pre-wrap",
                }}>
                  {limpiarFormato(m.content)}
                </div>
              </div>
            ))}
            {enviando && (
              <div style={{ display: "flex", justifyContent: "flex-start" }}>
                <div style={{ padding: "11px 15px", borderRadius: "16px 16px 16px 4px", background: "var(--glass)", border: "1px solid var(--glass-border)", color: "var(--text-3)", fontSize: "0.9rem" }}>
                  Pensando...
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {
            <div style={{ padding: 16, borderTop: "1px solid var(--glass-border)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderRadius: 14, padding: "6px 6px 6px 14px" }}>
                <input
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && !e.shiftKey && enviar()}
                  placeholder="Escribe tu respuesta..."
                  disabled={enviando}
                  style={{ flex: 1, background: "none", border: "none", outline: "none", color: "var(--text)", fontSize: "0.9rem", fontFamily: "inherit" }}
                />
                <LiquidButton onClick={enviar} disabled={enviando || !input.trim()} className="text-white font-semibold !px-6 !py-2">Enviar</LiquidButton>
              </div>
            </div>
          }
        </GlassPanel>

        {destinoSeguimiento && (
          <div style={{ marginTop: 16 }}>
            <Link href={`/portafolio/${destinoSeguimiento}/seguimiento`}>
              <LiquidButton className="text-white font-semibold !px-8 !py-3">Ir a Seguimiento →</LiquidButton>
            </Link>
          </div>
        )}

        {/* Propuesta */}
        {propuesta && (
          <PropuestaEditor
            key={Object.keys(propuesta.pesos).sort().join(",")}
            propuesta={propuesta}
            tieneInv={tieneInv}
            onAplicar={aplicar}
            aplicando={aplicando}
            msgEstado={msgEstado}
          />
        )}

      </>
  );
}

// Extrae un objeto JSON de un texto (el analista a veces lo envuelve en texto)
function extraerJSON(texto: string): Record<string, unknown> | null {
  try {
    const match = texto.match(/\{[\s\S]*\}/);
    if (!match) return null;
    return JSON.parse(match[0]);
  } catch {
    return null;
  }
}

// Quita markdown que el modelo a veces mete pese a las instrucciones
function limpiarFormato(texto: string): string {
  return texto
    .replace(/\*\*(.+?)\*\*/g, "$1")   // **negrita** → negrita
    .replace(/\*(.+?)\*/g, "$1")       // *cursiva* → cursiva
    .replace(/^[\s]*[•\-\*]\s+/gm, "") // viñetas al inicio de línea
    .trim();
}

const s: Record<string, React.CSSProperties> = {
  load: { background: "var(--bg)", color: "var(--text-3)", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 },
};