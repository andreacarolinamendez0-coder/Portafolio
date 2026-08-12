"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { authMe, authLogout, getPreciosRT, type PrecioRT, type RangoTicker } from "@/lib/api";
import { GlassPanel } from "@/components/ui/glass-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { PageIntro } from "@/components/ui/page-intro";
import { GlowCard } from "@/components/ui/spotlight-card";
import { AnimatedValue } from "@/components/ui/animated-value";
import { justificacionActivo, resumenPortafolio } from "@/lib/monitor-texto";

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

// El backend solo emite ENTRAR / VIGILAR / NEUTRAL (ver monitor.py) —
// no COMPRAR/VENDER. #ffd60a es el amarillo de "advertencia/pendiente"
// ya usado en el resto de la app (ver globals.css --yellow, badges de
// "Pendiente" en selector-portafolios.tsx y page.tsx).
const senalColor = (s: string) => s === "ENTRAR" ? "#30d158" : s === "VIGILAR" ? "#ffd60a" : "#6e6e73";
const rsiColor = (rsi: number) => rsi > 70 ? "#ff453a" : rsi < 30 ? "#30d158" : "#a1a1a6";
const numStyle = { fontVariantNumeric: "tabular-nums" as const };

function senalDe(data: PrecioRT | RangoTicker): string {
  if ("senal" in data) return data.senal;
  return data.puede_entrar ? "ENTRAR" : data.puede_vigilar ? "VIGILAR" : "NEUTRAL";
}

// ── Card de ticker (grid) ────────────────────────────────────
function TickerCard({
  ticker, data, live, seleccionado, obsoleto, flash, onClick,
}: {
  ticker: string;
  data: PrecioRT | RangoTicker;
  live: boolean;
  seleccionado: boolean;
  obsoleto: boolean;
  flash?: "up" | "down";
  onClick: () => void;
}) {
  const senal = senalDe(data);
  // GlowCard no tiene forma de quedar "sin glow": glowColor tiene default
  // 'blue' en la firma del componente, y un parámetro con default se activa
  // igual si la prop está ausente que si se pasa `undefined` explícito (así
  // es el destructuring en JS). Para NEUTRAL usamos GlassPanel en su lugar,
  // que no trae ningún acento de color.
  const rsi = data.rsi ?? 0;
  const p = live ? (data as PrecioRT) : null;
  const Contenedor = senal === "NEUTRAL" ? GlassPanel : GlowCard;
  const propsContenedor =
    senal === "ENTRAR"
      ? { glowColor: "green" as const, padding: "16px 18px" }
      : senal === "VIGILAR"
      ? { glowColor: "orange" as const, padding: "16px 18px" }
      : { style: { borderRadius: 16, padding: "16px 18px", marginBottom: 0 } };

  return (
    <div
      onClick={onClick}
      style={{
        cursor: "pointer",
        borderRadius: 16,
        opacity: obsoleto ? 0.55 : 1,
        boxShadow: seleccionado ? "0 0 0 2px rgba(10,132,255,0.6)" : "none",
        transition: "box-shadow 150ms ease, opacity 200ms ease",
      }}
    >
      <Contenedor {...propsContenedor}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <strong style={{ color: "#f5f5f7", fontSize: "0.95rem" }}>
            {ticker}
            {obsoleto && <span title="Dato desactualizado" style={{ marginLeft: 6, fontSize: 11, color: "#ffd60a" }}>⚠</span>}
          </strong>
          <span style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.04em", color: senalColor(senal),
            background: `${senalColor(senal)}22`, padding: "2px 8px", borderRadius: 980,
          }}>
            {senal}
          </span>
        </div>

        {p && (
          <>
            <div className={flash ? `flash-${flash}` : ""} style={{ fontSize: "1.1rem", fontWeight: 600, color: "#f5f5f7", marginBottom: 4, ...numStyle }}>
              <AnimatedValue
                value={p.precio ?? 0}
                format={(n) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              />
            </div>
            <div style={{
              fontSize: 12, fontWeight: 500, marginBottom: 10, ...numStyle,
              color: p.cambio_dia > 0 ? "#30d158" : p.cambio_dia < 0 ? "#ff453a" : "#a1a1a6",
            }}>
              {p.cambio_dia > 0 ? "▲ " : p.cambio_dia < 0 ? "▼ " : ""}{Math.abs(p.cambio_dia ?? 0).toFixed(1)}%
            </div>
          </>
        )}

        <div style={{ fontSize: 10, color: "#6e6e73", marginBottom: 4, display: "flex", justifyContent: "space-between" }}>
          <span>RSI</span><span>{rsi.toFixed(1)}</span>
        </div>
        <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${Math.min(100, Math.max(0, rsi))}%`, background: rsiColor(rsi), transition: "width 300ms ease" }} />
        </div>
      </Contenedor>
    </div>
  );
}

// ── Panel de detalle de un ticker seleccionado ───────────────
function DetallePanel({ ticker, data, live }: { ticker: string; data: PrecioRT | RangoTicker; live: boolean }) {
  const p = live ? (data as PrecioRT) : null;
  const metricas = [
    { label: "RSI", value: data.rsi != null ? data.rsi.toFixed(1) : "—" },
    { label: "MACD", value: data.hist_subiendo ? "Alcista ↑" : "Sin impulso" },
    { label: "Bollinger", value: data.banda_inf ? `$${data.banda_inf.toFixed(2)}` : "—" },
    { label: "Volumen", value: data.vol_ratio ? `${data.vol_ratio.toFixed(1)}x` : "—" },
  ];

  return (
    <GlassPanel style={{ marginTop: 20 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 18 }}>
        <h3 style={{ fontSize: "1.15rem", fontWeight: 600, color: "#f5f5f7", margin: 0 }}>{ticker}</h3>
        {p && (
          <span style={{ fontSize: "1.1rem", fontWeight: 600, color: "#f5f5f7", ...numStyle }}>
            <AnimatedValue
              value={p.precio ?? 0}
              format={(n) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            />
          </span>
        )}
        <span style={{ fontSize: 12, fontWeight: 600, color: senalColor(senalDe(data)) }}>{senalDe(data)}</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 18 }}>
        {metricas.map(m => (
          <div key={m.label}>
            <p style={{ fontSize: 11, color: "#6e6e73", textTransform: "uppercase", letterSpacing: "0.06em", margin: "0 0 4px" }}>{m.label}</p>
            <p style={{ fontSize: 14, fontWeight: 600, color: "#f5f5f7", margin: 0, ...numStyle }}>{m.value}</p>
          </div>
        ))}
      </div>

      <p style={{ fontSize: 13, color: "#a1a1a6", lineHeight: 1.6, margin: 0 }}>{justificacionActivo(data, ticker)}</p>
    </GlassPanel>
  );
}

export default function MonitorPage() {
  const router  = useRouter();
  const params  = useParams();
  const archivo = params.archivo as string;

  const [precios, setPrecios]   = useState<Record<string, PrecioRT>>({});
  const [rangos, setRangos]     = useState<Record<string, RangoTicker>>({});
  const [rangosFecha, setRF]    = useState("");
  const [mercadoAbierto, setMA] = useState(false);
  const [ultimoUpdate, setUU]   = useState("");
  const [macdSinConfirmar, setMSC] = useState(0);
  const [loading, setLoading]   = useState(true);
  const [flash, setFlash]       = useState<Record<string, "up" | "down">>({});
  const [estado, setEstado]     = useState<EstadoCarga>("");
  const [errorMsg, setErrorMsg] = useState("");
  const [selected, setSelected] = useState("");
  const [progress, setProgress] = useState(0);

  const prevPrecios = useRef<Record<string, number>>({});
  const flashTimer  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastLoadRef = useRef<number>(Date.now());

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
        setMSC(data.macd_sin_confirmacion_total ?? 0);
        setEstado("");
        setErrorMsg("");
        lastLoadRef.current = Date.now();

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

  // Anillo de "próximo refresh" — se llena a lo largo de REFRESH_MS desde el
  // último dato recibido con éxito. Es honesto con el ciclo real del
  // navegador (no simula un ciclo del backend que el frontend no conoce).
  useEffect(() => {
    const t = setInterval(() => {
      const transcurrido = Date.now() - lastLoadRef.current;
      setProgress(Math.min(100, (transcurrido / REFRESH_MS) * 100));
    }, 100);
    return () => clearInterval(t);
  }, []);

  if (loading) return <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)", color: "var(--text-3)", fontSize: 14 }}>Cargando...</div>;

  const hayPrecios = Object.keys(precios).length > 0;
  const itemsActuales: Record<string, PrecioRT | RangoTicker> = hayPrecios ? precios : rangos;
  const tickersActuales = Object.keys(itemsActuales);
  const tickerSeleccionado = (selected && tickersActuales.includes(selected)) ? selected : tickersActuales[0];
  const dataSeleccionada = tickerSeleccionado ? itemsActuales[tickerSeleccionado] : null;

  return (
    <>
      <style>{`
        @keyframes flashUp   { 0% { background: rgba(48,209,88,0.22); } 100% { background: transparent; } }
        @keyframes flashDown { 0% { background: rgba(255,69,58,0.22); } 100% { background: transparent; } }
        .flash-up   { animation: flashUp   0.9s ease-out; }
        .flash-down { animation: flashDown 0.9s ease-out; }
      `}</style>

    <PageIntro
      archivo={archivo}
      texto="Precios en tiempo real de tus activos con señales técnicas (RSI, medias móviles) para ayudarte a decidir cuándo entrar o salir. Recuerda, es una sugerencia basada en datos históricos y no constituye asesoramiento financiero."
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

      {hayPrecios && (
        <GlassPanel style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
            <div>
              <p style={{ fontSize: 13, color: "#f5f5f7", margin: 0 }}>{resumenPortafolio(precios)}</p>
              {macdSinConfirmar > 0 && (
                <p style={{ fontSize: 12, color: "#6e6e73", margin: "6px 0 0" }}>
                  {macdSinConfirmar} {macdSinConfirmar === 1 ? "entrada" : "entradas"} hoy sin confirmación de momentum
                </p>
              )}
            </div>
            <div
              title="Próximo refresh"
              style={{
                width: 30, height: 30, borderRadius: "50%", flexShrink: 0, position: "relative",
                background: `conic-gradient(#0a84ff ${progress * 3.6}deg, rgba(255,255,255,0.08) 0deg)`,
                transition: "background 100ms linear",
              }}
            >
              <div style={{ position: "absolute", inset: 3, borderRadius: "50%", background: "var(--bg-elevated, #1c1c1e)" }} />
            </div>
          </div>
        </GlassPanel>
      )}

      {!hayPrecios ? (
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
          <>
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
              {rangosFecha && Object.keys(rangos).length > 0 && (
                <p style={{ color: "var(--text-3)", fontSize: 11, margin: "16px 0 0" }}>
                  Rangos calculados para {rangosFecha}
                </p>
              )}
            </GlassPanel>

            {Object.keys(rangos).length > 0 && (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px,1fr))", gap: 14, marginTop: 20 }}>
                  {Object.entries(rangos).map(([ticker, r]) => (
                    <TickerCard
                      key={ticker}
                      ticker={ticker}
                      data={r}
                      live={false}
                      seleccionado={ticker === tickerSeleccionado}
                      obsoleto={false}
                      onClick={() => setSelected(ticker)}
                    />
                  ))}
                </div>
                {dataSeleccionada && tickerSeleccionado && (
                  <DetallePanel ticker={tickerSeleccionado} data={dataSeleccionada} live={false} />
                )}
              </>
            )}
          </>
        )
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px,1fr))", gap: 14 }}>
            {Object.entries(precios).map(([ticker, p]) => {
              const obsoleto = mercadoAbierto && esObsoleto(p.timestamp);
              return (
                <TickerCard
                  key={ticker}
                  ticker={ticker}
                  data={p}
                  live={true}
                  seleccionado={ticker === tickerSeleccionado}
                  obsoleto={obsoleto}
                  flash={flash[ticker]}
                  onClick={() => setSelected(ticker)}
                />
              );
            })}
          </div>
          {dataSeleccionada && tickerSeleccionado && (
            <DetallePanel ticker={tickerSeleccionado} data={dataSeleccionada} live={true} />
          )}
        </>
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
