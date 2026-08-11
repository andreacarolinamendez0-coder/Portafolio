"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { authMe, authLogout, getPreciosRT, type PrecioRT, type RangoTicker } from "@/lib/api";
import { GlassPanel } from "@/components/ui/glass-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { PageIntro } from "@/components/ui/page-intro";

// Lee el precio cacheado del backend. El server refresca Finnhub ~cada 9s;
// el frontend consulta más seguido para que el display se sienta vivo.
const REFRESH_MS = 4000;

// Los timestamps por fila vienen en hora Colombia (UTC-5 fijo, sin DST) con
// formato "YYYY-MM-DD HH:MM:SS" (ver monitor.py, hora_colombia()). Margen
// antes de considerar una fila "obsoleta": el backend refresca cada ~9-15s
// y el frontend hace polling cada 4s, así que 40s da colchón contra jitter
// de red sin generar falsos positivos.
const UMBRAL_OBSOLETO_MS = 40_000;

function esObsoleto(timestamp: string): boolean {
  if (!timestamp) return false;
  const t = new Date(timestamp.replace(" ", "T") + "-05:00").getTime();
  if (Number.isNaN(t)) return false;
  return Date.now() - t > UMBRAL_OBSOLETO_MS;
}

type EstadoCarga = "" | "sin_inicializar" | "error_backend" | "error_red";

export default function MonitorPage() {
  const router  = useRouter();
  const params  = useParams();
  const archivo = params.archivo as string;

  const [precios, setPrecios]   = useState<Record<string, PrecioRT>>({});
  const [rangos, setRangos]     = useState<Record<string, RangoTicker>>({});
  const [rangosFecha, setRF]    = useState("");
  const [mercadoAbierto, setMA] = useState(false);
  const [ultimoUpdate, setUU]   = useState("");
  const [loading, setLoading]   = useState(true);
  const [flash, setFlash]       = useState<Record<string, "up" | "down">>({});
  const [estado, setEstado]     = useState<EstadoCarga>("");
  const [errorMsg, setErrorMsg] = useState("");

  const prevPrecios = useRef<Record<string, number>>({});
  const flashTimer  = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    let redirigiendo = false;
    try {
      const me = await authMe();
      if (!me.authenticated) { redirigiendo = true; router.push("/login"); return; }
      const data = await getPreciosRT(archivo);
      if (data.ok) {
        const nuevos = data.precios ?? {};

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
        setRangos(data.rangos ?? {});
        setRF(data.rangos_fecha ?? "");
        setMA(data.mercado_abierto);
        setUU(data.ultimo_update);
        setEstado("");
        setErrorMsg("");

        if (Object.keys(nuevoFlash).length) {
          setFlash(nuevoFlash);
          if (flashTimer.current) clearTimeout(flashTimer.current);
          flashTimer.current = setTimeout(() => setFlash({}), 900);
        }
      } else {
        // El backend respondió pero sin datos utilizables — distinguir
        // "monitor nunca inicializado" de un error real de backend.
        setPrecios({});
        setRangos({});
        if (data.error === "Sin datos aún") {
          setEstado("sin_inicializar");
        } else {
          setEstado("error_backend");
        }
        setErrorMsg(data.error ?? "");
      }
    } catch {
      // Falla real de red/fetch — no confundir con "todo funcionando".
      setEstado("error_red");
    } finally {
      if (!redirigiendo) setLoading(false);
    }
  }, [archivo, router]);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => { clearInterval(t); if (flashTimer.current) clearTimeout(flashTimer.current); };
  }, [load]);

  // El backend solo emite ENTRAR / VIGILAR / NEUTRAL (ver monitor.py) —
  // no COMPRAR/VENDER. #ffd60a es el amarillo de "advertencia/pendiente"
  // ya usado en el resto de la app (ver globals.css --yellow, badges de
  // "Pendiente" en selector-portafolios.tsx y page.tsx).
  const senalColor = (s: string) => s === "ENTRAR" ? "#30d158" : s === "VIGILAR" ? "#ffd60a" : "#6e6e73";
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
        estado === "error_red" ? (
          <GlassPanel style={{ padding: "32px", textAlign: "center" }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ff453a", display: "inline-block" }} />
              <span style={{ color: "#ff453a", fontSize: 14, fontWeight: 600 }}>No se pudo conectar</span>
            </div>
            <p style={{ color: "var(--text-2)", fontSize: 14, margin: "0 0 6px" }}>
              No se pudo cargar el monitor. Revisa tu conexión e intenta de nuevo.
            </p>
          </GlassPanel>
        ) : estado === "error_backend" ? (
          <GlassPanel style={{ padding: "32px", textAlign: "center" }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ff453a", display: "inline-block" }} />
              <span style={{ color: "#ff453a", fontSize: 14, fontWeight: 600 }}>Error del servidor</span>
            </div>
            <p style={{ color: "var(--text-2)", fontSize: 14, margin: "0 0 6px" }}>
              El monitor reportó un error{errorMsg ? `: ${errorMsg}` : "."}
            </p>
          </GlassPanel>
        ) : estado === "sin_inicializar" ? (
          <GlassPanel style={{ padding: "32px", textAlign: "center" }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ffd60a", display: "inline-block" }} />
              <span style={{ color: "#ffd60a", fontSize: 14, fontWeight: 600 }}>Monitor aún sin inicializar</span>
            </div>
            <p style={{ color: "var(--text-2)", fontSize: 14, margin: "0 0 6px" }}>
              Este portafolio todavía no tiene un primer ciclo de monitoreo registrado.
            </p>
            <p style={{ color: "var(--text-3)", fontSize: 12, margin: 0 }}>
              Debería activarse en el próximo ciclo del monitor. Si sigue así después de un rato, revisa que el monitoreo esté activo.
            </p>
          </GlassPanel>
        ) : mercadoAbierto ? (
          <GlassPanel style={{ padding: "32px", textAlign: "center" }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ffd60a", display: "inline-block" }} />
              <span style={{ color: "#ffd60a", fontSize: 14, fontWeight: 600 }}>Esperando datos</span>
            </div>
            <p style={{ color: "var(--text-2)", fontSize: 14, margin: "0 0 6px" }}>
              El mercado está abierto pero el monitor todavía no trajo precios para este portafolio.
            </p>
            <p style={{ color: "var(--text-3)", fontSize: 12, margin: 0 }}>
              Debería llegar en el próximo ciclo (cada pocos segundos). Si persiste, avisa para revisar el monitor.
            </p>
          </GlassPanel>
        ) : (
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
            {Object.keys(rangos).length > 0 && (
              <div style={{ marginTop: 20, textAlign: "left" }}>
                {rangosFecha && (
                  <p style={{ color: "var(--text-3)", fontSize: 11, margin: "0 0 10px" }}>
                    Rangos calculados para {rangosFecha}
                  </p>
                )}
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      {["Activo","Rango para entrar","Rango para vigilar","Estado"].map(h => (
                        <th key={h} style={{ fontSize: "0.7rem", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase", color: "#6e6e73", padding: "10px 14px", textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(rangos).map(([ticker, r]) => (
                      <tr key={ticker} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                        <td style={{ padding: "12px 14px", fontSize: "0.85rem" }}><strong style={{ color: "#f5f5f7" }}>{ticker}</strong></td>
                        <td style={{ padding: "12px 14px", fontSize: "0.85rem", color: "#a1a1a6", ...num }}>
                          {r.rango_entrar != null ? `$${r.rango_entrar.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
                        </td>
                        <td style={{ padding: "12px 14px", fontSize: "0.85rem", color: "#a1a1a6", ...num }}>
                          {r.rango_vigilar != null ? `$${r.rango_vigilar.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
                        </td>
                        <td style={{ padding: "12px 14px", fontSize: "0.85rem" }}>
                          {r.puede_entrar
                            ? <span style={{ color: "#30d158", fontWeight: 600 }}>Puede entrar</span>
                            : r.puede_vigilar
                              ? <span style={{ color: "#ffd60a", fontWeight: 600 }}>Vigilar</span>
                              : <span style={{ color: "#6e6e73" }}>Neutral</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </GlassPanel>
        )
      ) : (
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
              {Object.entries(precios).map(([ticker, p]) => {
                const obsoleto = mercadoAbierto && esObsoleto(p.timestamp);
                return (
                  <tr key={ticker} className="mon-row" style={{ borderBottom: "1px solid rgba(255,255,255,0.04)", opacity: obsoleto ? 0.55 : 1 }}>
                    <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}>
                      <strong style={{ color: "#f5f5f7" }}>{ticker}</strong>
                      {obsoleto && <span title="Dato desactualizado" style={{ marginLeft: 6, fontSize: 11, color: "#ffd60a" }}>⚠</span>}
                    </td>
                    <td className={flash[ticker] ? `flash-${flash[ticker]}` : ""} style={{ padding: "14px 16px", fontSize: "0.9rem", fontWeight: 600, color: obsoleto ? "#8e8e93" : "#f5f5f7", ...num }}>
                      ${p.precio?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: "14px 16px", fontSize: "0.875rem", fontWeight: 500, color: p.cambio_dia > 0 ? "#30d158" : p.cambio_dia < 0 ? "#ff453a" : "#a1a1a6", ...num }}>{p.cambio_dia > 0 ? "▲ " : p.cambio_dia < 0 ? "▼ " : ""}{Math.abs(p.cambio_dia ?? 0).toFixed(1)}%</td>
                    <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: p.rsi > 70 ? "#ff453a" : p.rsi < 30 ? "#30d158" : "#a1a1a6", ...num }}>{p.rsi?.toFixed(1)}</td>
                    <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6", ...num }}>{p.ma20?.toFixed(2)}</td>
                    <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6", ...num }}>{p.ma50?.toFixed(2)}</td>
                    <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}><span style={{ color: senalColor(p.senal), fontWeight: 600 }}>{p.senal}</span></td>
                    <td style={{ padding: "14px 16px", fontSize: "0.875rem", color: "#a1a1a6", ...num }}>{p.score}</td>
                    <td style={{ padding: "14px 16px", fontSize: "0.875rem" }}>{p.puede_entrar ? <span style={{ color: "#30d158", fontWeight: 600 }}>✓ Sí</span> : <span style={{ color: "#6e6e73" }}>—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </GlassPanel>
      )}

      <div style={{ marginTop: 24, display: "flex", gap: 10 }}>
        <LiquidButton onClick={load} className="text-white font-semibold !px-8 !py-2.5">Actualizar ahora</LiquidButton>
        <Link href={`/portafolio/${archivo}`}>
          <LiquidButton className="text-white font-semibold !px-8 !py-2.5">Ir al Dashboard</LiquidButton>
        </Link>
      </div>
    </>
  );
}