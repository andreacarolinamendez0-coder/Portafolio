"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { authMe, authLogout, getPreciosRT } from "@/lib/api";
import { GlassPanel } from "@/components/ui/glass-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { PageIntro } from "@/components/ui/page-intro";
import { div } from "framer-motion/m";

interface PrecioRT {
  precio:        number;
  cambio_dia:    number;
  senal:         string;
  score:         number;
  rsi:           number;
  ma20:          number;
  ma50:          number;
  puede_entrar:  boolean;
  mercado_rt:    boolean;
  timestamp:     string;
}

// Lee el precio cacheado del backend. El server refresca Finnhub ~cada 9s;
// el frontend consulta más seguido para que el display se sienta vivo.
const REFRESH_MS = 4000;

export default function MonitorPage() {
  const router  = useRouter();
  const params  = useParams();
  const archivo = params.archivo as string;

  const [precios, setPrecios]   = useState<Record<string, PrecioRT>>({});
  const [mercadoAbierto, setMA] = useState(false);
  const [ultimoUpdate, setUU]   = useState("");
  const [loading, setLoading]   = useState(true);
  const [flash, setFlash]       = useState<Record<string, "up" | "down">>({});

  const prevPrecios = useRef<Record<string, number>>({});
  const flashTimer  = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const me = await authMe();
      if (!me.authenticated) { router.push("/login"); return; }
      const data = await getPreciosRT(archivo);
      if (data.ok) {
        const nuevos = data.precios as Record<string, PrecioRT>;

        // Detectar qué precios cambiaron para el parpadeo tipo broker
        const nuevoFlash: Record<string, "up" | "down"> = {};
        for (const [ticker, p] of Object.entries(nuevos)) {
          const anterior = prevPrecios.current[ticker];
          if (anterior !== undefined && p.precio !== anterior) {
            nuevoFlash[ticker] = p.precio > anterior ? "up" : "down";
          }
          prevPrecios.current[ticker] = p.precio;
        }

        setPrecios(nuevos);
        setMA(data.mercado_abierto);
        setUU(data.ultimo_update);

        if (Object.keys(nuevoFlash).length) {
          setFlash(nuevoFlash);
          if (flashTimer.current) clearTimeout(flashTimer.current);
          flashTimer.current = setTimeout(() => setFlash({}), 900);
        }
      }
    } catch { /* aún sin precios */ } finally {
      setLoading(false);
    }
  }, [archivo, router]);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => { clearInterval(t); if (flashTimer.current) clearTimeout(flashTimer.current); };
  }, [load]);

  const senalColor = (s: string) => s === "COMPRAR" ? "#30d158" : s === "VENDER" ? "#ff453a" : "#6e6e73";
  const num = { fontVariantNumeric: "tabular-nums" as const };

  if (loading) return <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)", color: "var(--text-3)", fontSize: 14 }}>Cargando...</div>;

  return (
    <>
      <style>{`
        @keyframes flashUp   { 0% { background: rgba(48,209,88,0.22); } 100% { background: transparent; } }
        @keyframes flashDown { 0% { background: rgba(255,69,58,0.22); } 100% { background: transparent; } }
        .flash-up   { animation: flashUp   0.9s ease-out; }
        .flash-down { animation: flashDown 0.9s ease-out; }
        .mon-row:hover { background: rgba(255,255,255,0.025); }
      `}</style>
      
    <PageIntro
      archivo={archivo}
      texto="Precios en tiempo real de tus activos con señales técnicas (RSI, medias móviles) para ayudarte a decidir cuándo entrar o salir."
    />

      {/* Barra de estado en vivo */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        {mercadoAbierto
          ? <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#30d158", padding: "5px 12px", borderRadius: 980, background: "rgba(48,209,88,0.08)", border: "1px solid rgba(48,209,88,0.2)" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#30d158", animation: "pulse-dot 2s infinite", display: "inline-block" }} />
              En vivo · mercado abierto
            </span>
          : <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#6e6e73", padding: "5px 12px", borderRadius: 980, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#6e6e73", display: "inline-block" }} />
              Mercado cerrado
            </span>}
        {ultimoUpdate && <span style={{ fontSize: 12, color: "#6e6e73" }}>Actualizado: {ultimoUpdate}</span>}
        <button onClick={async () => { await authLogout(); router.push("/login"); }} style={{ marginLeft: "auto", background: "none", border: "none", color: "#6e6e73", fontSize: 12, cursor: "pointer" }}>Salir</button>
      </div>

      {Object.keys(precios).length === 0 ? (
  <GlassPanel style={{ padding: "32px", textAlign: "center" }}>
    <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#30d158", display: "inline-block" }} />
      <span style={{ color: "#30d158", fontSize: 14, fontWeight: 600 }}>Monitoreo activo</span>
    </div>
    <p style={{ color: "var(--text-2)", fontSize: 14, margin: "0 0 6px" }}>
      Todo funcionando correctamente. El mercado está cerrado ahora mismo.
    </p>
    <p style={{ color: "var(--text-3)", fontSize: 12, margin: 0 }}>
      Ya calculé tus rangos del día. Los precios en vivo empiezan a las 9:30am (NY).
    </p>
  </GlassPanel>
) : (
  <GlassPanel style={{ overflowX: "auto" }}>
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      {/* ...toda tu tabla de precios... */}
    </table>
  </GlassPanel>
)}
        <GlassPanel style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["Activo","Precio","Cambio %","RSI","MA 20","MA 50","Señal","Score","Puede entrar"].map(h => (
                  <th key={h} style={{ fontSize: "0.7rem", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase", color: "#6e6e73", padding: "12px 16px", textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.04)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(precios).map(([ticker, p]) => (
                <tr key={ticker} className="mon-row" style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}><strong style={{ color: "#f5f5f7" }}>{ticker}</strong></td>
                  <td className={flash[ticker] ? `flash-${flash[ticker]}` : ""} style={{ padding: "14px 16px", fontSize: "0.9rem", fontWeight: 600, color: "#f5f5f7", ...num }}>${p.precio?.toFixed(2)}</td>
                  <td style={{ padding: "14px 16px", fontSize: "0.875rem", fontWeight: 500, color: p.cambio_dia > 0 ? "#30d158" : p.cambio_dia < 0 ? "#ff453a" : "#a1a1a6", ...num }}>{p.cambio_dia > 0 ? "▲ " : p.cambio_dia < 0 ? "▼ " : ""}{Math.abs(p.cambio_dia ?? 0).toFixed(2)}%</td>
                  <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: p.rsi > 70 ? "#ff453a" : p.rsi < 30 ? "#30d158" : "#a1a1a6", ...num }}>{p.rsi?.toFixed(1)}</td>
                  <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6", ...num }}>{p.ma20?.toFixed(2)}</td>
                  <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6", ...num }}>{p.ma50?.toFixed(2)}</td>
                  <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}><span style={{ color: senalColor(p.senal), fontWeight: 600 }}>{p.senal}</span></td>
                  <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6", ...num }}>{p.score}</td>
                  <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}>{p.puede_entrar ? <span style={{ color: "#30d158", fontWeight: 600 }}>✓ Sí</span> : <span style={{ color: "#6e6e73" }}>—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassPanel>
      

      <div style={{ marginTop: 24, display: "flex", gap: 10 }}>
        <LiquidButton onClick={load} className="text-white font-semibold !px-8 !py-2.5">Actualizar ahora</LiquidButton>
        <Link href={`/portafolio/${archivo}`}>
          <LiquidButton className="text-white font-semibold !px-8 !py-2.5">Ir al Dashboard</LiquidButton>
        </Link>
      </div>
    </>
  );
}