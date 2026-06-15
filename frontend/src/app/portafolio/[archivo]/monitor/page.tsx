"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { LogoMark } from "@/components/ui/logo";
import { authMe, authLogout, getPreciosRT } from "@/lib/api";
import { GlassBackground } from "@/components/ui/glass-background";
import { GlassPanel } from "@/components/ui/glass-panel";
import { GlowPanel } from "@/components/ui/glow-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";

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

export default function MonitorPage() {
  const router  = useRouter();
  const params  = useParams();
  const archivo = params.archivo as string;

  const [precios, setPrecios]   = useState<Record<string, PrecioRT>>({});
  const [mercadoAbierto, setMA] = useState(false);
  const [ultimoUpdate, setUU]   = useState("");
  const [loading, setLoading]   = useState(true);

  const load = useCallback(async () => {
    try {
      const me = await authMe();
      if (!me.authenticated) { router.push("/login"); return; }
      const data = await getPreciosRT(archivo);
      if (data.ok) {
        setPrecios(data.precios as Record<string, PrecioRT>);
        setMA(data.mercado_abierto);
        setUU(data.ultimo_update);
      }
    } catch { /* no prices yet */ } finally {
      setLoading(false);
    }
  }, [archivo, router]);

  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);

  const senalColor = (s: string) => s === "COMPRAR" ? "#30d158" : s === "VENDER" ? "#ff453a" : "#6e6e73";

  if (loading) return <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)", color: "var(--text-3)", fontSize: 14 }}>Cargando...</div>;
  
  return (
    <GlassBackground>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <LogoMark size={32} />
          <Link href={`/portafolio/${archivo}`} style={{ color: "var(--text-3)", fontSize: 12, textDecoration: "none" }}>← Dashboard</Link>
          <span style={{ color: "var(--text-3)", fontSize: 12 }}>/ Monitor</span>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
            {mercadoAbierto
              ? <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "#30d158", padding: "5px 12px", borderRadius: 980, background: "rgba(48,209,88,0.08)", border: "1px solid rgba(48,209,88,0.2)" }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#30d158", animation: "pulse-dot 2s infinite", display: "inline-block" }} />
                  Mercado abierto
                </span>
              : <span style={{ fontSize: 12, color: "#6e6e73" }}>Mercado cerrado</span>}
            <button onClick={async () => { await authLogout(); router.push("/login"); }} style={{ background: "none", border: "none", color: "#6e6e73", fontSize: 12, cursor: "pointer" }}>Salir</button>
          </div>
        </div>

        {Object.keys(precios).length === 0 ? (
          <GlassPanel style={{ padding: "40px", textAlign: "center" }}>
            <p style={{ color: "var(--text-3)" }}>Sin datos de precios en tiempo real.</p>
            <p style={{ color: "var(--text-3)", fontSize: 12, marginTop: 8 }}>El monitor necesita estar activo y tener datos de precios del portfolio.</p>
          </GlassPanel>
        ) : (
          <>
            <GlassPanel style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Activo","Precio","Cambio %","RSI","MA 20","MA 50","Señal","Score","Puede entrar"].map(h => (
                      <th key={h} style={{ fontSize: "0.7rem", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase", color: "#6e6e73", padding: "10px 16px", textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.04)" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(precios).map(([ticker, p]) => (
                    <tr key={ticker} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}><strong style={{ color: "#f5f5f7" }}>{ticker}</strong></td>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6" }}>${p.precio?.toFixed(2)}</td>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: p.cambio_dia > 0 ? "#30d158" : "#ff453a", fontWeight: 500 }}>{p.cambio_dia > 0 ? "+" : ""}{p.cambio_dia?.toFixed(2)}%</td>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: p.rsi > 70 ? "#ff453a" : p.rsi < 30 ? "#30d158" : "#a1a1a6" }}>{p.rsi?.toFixed(1)}</td>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6" }}>{p.ma20?.toFixed(2)}</td>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6" }}>{p.ma50?.toFixed(2)}</td>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}>
                        <span style={{ color: senalColor(p.senal), fontWeight: 600 }}>{p.senal}</span>
                      </td>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6" }}>{p.score}</td>
                      <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}>
                        {p.puede_entrar
                          ? <span style={{ color: "#30d158", fontWeight: 600 }}>✓ Sí</span>
                          : <span style={{ color: "#6e6e73" }}>—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </GlassPanel>
            {ultimoUpdate && <p style={{ color: "#6e6e73", fontSize: 11, textAlign: "right", marginTop: 8 }}>Actualizado: {ultimoUpdate}</p>}
          </>
        )}

        <div style={{ marginTop: 24, display: "flex", gap: 10 }}>
          <LiquidButton onClick={load} className="text-white font-semibold !px-8 !py-2.5">
            Actualizar precios
          </LiquidButton>
          <Link href={`/portafolio/${archivo}`}>
            <LiquidButton className="text-white font-semibold !px-8 !py-2.5">
              Ir al Dashboard
            </LiquidButton>
          </Link>
        </div>
      </div>
    </GlassBackground>
  );
}
