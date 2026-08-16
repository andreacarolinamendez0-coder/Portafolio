"use client";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { MagneticTabs } from "@/components/ui/magnetic-tabs";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { GlowCard } from "@/components/ui/spotlight-card";
import { GlassBackground } from "@/components/ui/glass-background";
import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { LogoMark } from "@/components/ui/logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionTitle } from "@/components/ui/card";
import { authMe, authLogout, triggerRecolector, getUltimaActualizacion, getPreciosRT, type DashboardData, type Posicion, type PrecioRT, type RangoTicker, type MonitoreoMap } from "@/lib/api";
import { getDashboard, getTrmAnalisis, getHistoricoAnalisis } from "@/lib/api";
import { style } from "framer-motion/client";
import { PageIntro } from "@/components/ui/page-intro";
import {getConfig} from "@/lib/api";
import { mostrarMonto, type Divisa } from "@/lib/divisas";
import { AnimatedValue } from "@/components/ui/animated-value";
import { AvisoSeguimiento } from "@/components/ui/aviso-seguimiento";
import { AvisosHost } from "@/components/ui/aviso-flotante";
import { AvisoSenalesMonitor } from "@/components/ui/aviso-senales-monitor";
import { AvisoTrm } from "@/components/ui/aviso-trm";

interface MonitorAmbient {
  mercadoAbierto: boolean;
  precios:        Record<string, PrecioRT>;
  rangos:         Record<string, RangoTicker>;
  monitoreo:      MonitoreoMap;
}

// Métricas recalculadas en vivo (polling de /api/precios-rt) que sobrescriben
// total_valor / ganancia_total / rentabilidad_total mientras hay monitoreo activo.
interface MetricasVivas {
  total_valor:        number;
  ganancia_total:     number;
  rentabilidad_total: number;
}

// Tabs: "hoy" | "historico"
type Tab = "hoy" | "historico";

export default function DashboardPage() {
  const router  = useRouter();
  const params  = useParams();
  const archivo = params.archivo as string;

  const [data, setData]           = useState<DashboardData | null>(null);
  const [tab, setTab]             = useState<Tab>("hoy");
  const [loading, setLoading]     = useState(true);
  const [updating, setUpdating]   = useState(false);
  const [lastUpdate, setLastUpdate] = useState("");
  const [username, setUsername]   = useState("");
  const [divisa, setDivisa] = useState<"USD" | "EUR" | "COP">("COP");
  const [liveTR, setLiveTR]       = useState<MetricasVivas | null>(null);
  // Datos de /api/precios-rt mas alla de liveTR (precios/rangos/monitoreo)
  // -- solo para que los avisos flotantes de Monitor sepan si hay señales
  // activas. Misma llamada que pollPrecios ya hacia, no es un fetch nuevo.
  const [monitorAmbient, setMonitorAmbient] = useState<MonitorAmbient | null>(null);

  // Ref con el último `data` cargado — el intervalo de polling lo lee para
  // no quedarse con un closure viejo (no se re-crea el interval en cada render).
  const dataRef = useRef<DashboardData | null>(null);
  useEffect(() => { dataRef.current = data; }, [data]);

  // Último precio en vivo conocido por ticker (USD), para no perder el valor
  // si un poll llega sin ese ticker (mercado cerrado momentáneamente, etc).
  const preciosVivosRef = useRef<Record<string, number>>({});

  // Evita que el polling pise los datos justo cuando "Actualizar datos" está
  // corriendo (triggerRecolector + load completo).
  const refrescandoRef = useRef(false);

  const load = useCallback(async () => {
    try {
      const me = await authMe();
      if (!me.authenticated) { router.push("/login"); return; }
      setUsername(me.username);
      const d = await getDashboard(archivo);
      setData(d);
      // Los valores en vivo se recalculan de nuevo sobre esta base fresca.
      setLiveTR(null);
      preciosVivosRef.current = {};
      if (d.tiempo_real) {
        for (const p of d.tiempo_real.posiciones) {
          preciosVivosRef.current[p.activo] = p.precio_hoy;
        }
      }
      const cfg = await getConfig(archivo);   // ← trae la divisa guardada
      setDivisa(cfg.divisa as "USD" | "EUR" | "COP");
      const { timestamp } = await getUltimaActualizacion();
      setLastUpdate(timestamp);
    } catch {
      router.push("/");
    } finally {
      setLoading(false);
    }
  }, [archivo, router]);

  // Polling liviano: solo /api/precios-rt (no getDashboard completo).
  // Recalcula total_valor/ganancia_total/rentabilidad_total en el cliente
  // usando las posiciones ya cargadas + el precio en vivo por ticker.
  // Base nativa USD (igual que calcular_tiempo_real en dashboard.py) — la
  // conversión a COP/EUR para mostrar ocurre en mostrarMonto(), no aquí.
  const pollPrecios = useCallback(async () => {
    if (refrescandoRef.current) return;
    const cur = dataRef.current;
    if (!cur || !cur.portafolio.monitoreo_activo) return;
    const tr = cur.tiempo_real;
    if (!tr || tr.posiciones.length === 0) return;

    try {
      const res = await getPreciosRT(archivo);
      if (!res.ok) return;

      setMonitorAmbient({
        mercadoAbierto: res.mercado_abierto,
        precios: res.precios ?? {},
        rangos: res.rangos ?? {},
        monitoreo: res.monitoreo ?? {},
      });

      if (!res.precios || Object.keys(res.precios).length === 0) return;

      for (const [ticker, info] of Object.entries(res.precios)) {
        if (info && typeof info.precio === "number" && info.precio > 0) {
          preciosVivosRef.current[ticker] = info.precio;
        }
      }

      let total_valor = 0;
      for (const p of tr.posiciones) {
        const precio = preciosVivosRef.current[p.activo] ?? p.precio_hoy;
        total_valor += p.fracciones * precio;
      }
      const total_invertido    = tr.total_invertido;
      const ganancia_total     = total_valor - total_invertido;
      const rentabilidad_total = total_invertido > 0 ? (ganancia_total / total_invertido) * 100 : 0;

      setLiveTR({ total_valor, ganancia_total, rentabilidad_total });
    } catch {
      // Poll silencioso: si falla, se dejan los últimos valores mostrados.
    }
  }, [archivo]);

  useEffect(() => {
    load();
    const id = setInterval(() => { pollPrecios(); }, 10000);
    return () => clearInterval(id);
  }, [load, pollPrecios]);

  async function handleLogout() {
    await authLogout();
    router.push("/login");
  }

  async function handleRefresh() {
    setUpdating(true);
    refrescandoRef.current = true;
    try {
      await triggerRecolector();
      await load();
    } finally {
      setUpdating(false);
      refrescandoRef.current = false;
    }
  }

  if (loading || !data) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg)" }}>
      <div style={{ color: "var(--text-3)", fontSize: 14 }}>Cargando portafolio...</div>
    </div>
  );

  const { portafolio, composicion, tiempo_real, historico, macro } = data;
  const perfil = portafolio.perfil;
  const gc     = tiempo_real && tiempo_real.ganancia_total > 0 ? "#30d158" : "#ff453a";

  // Métricas efectivas para las stat cards: si hay un poll en vivo reciente,
  // sobrescribe total_valor/ganancia_total/rentabilidad_total; el resto
  // (posiciones, total_invertido) se queda igual que en la última carga completa.
  const tiempoRealEfectivo = tiempo_real && liveTR
    ? { ...tiempo_real, ...liveTR }
    : tiempo_real;

  return (
    <>
    <style>{`
   .atom-hint:hover { background: rgba(0,113,227,0.2); border-color: rgba(0,113,227,0.5); }
   .atom-glow { animation: atomGlow 3s ease-in-out infinite; }
    @keyframes atomGlow {
    0%,100% { filter: drop-shadow(0 0 6px rgba(0,113,227,0.35)); }
    50%     { filter: drop-shadow(0 0 12px rgba(0,113,227,0.6)); }
    }
`   }</style>
        {/* Barra de ayuda de la página */}
<PageIntro
  archivo={archivo}
  texto="Aquí ves el resumen de tu portafolio: cuánto invertiste, cuánto vale hoy, tu ganancia y los indicadores macro que afectan tus inversiones."
/>

{/* Toggle Hoy / Histórico (botones glass, distinto del nav) */}
<div style={{ display: "flex", gap: 8, marginBottom: 28 }}>
  {([{ v: "hoy", l: "Hoy" }, { v: "historico", l: "Histórico" }] as const).map(t => {
    const active = tab === t.v;
    return (
      <button
        key={t.v}
        onClick={() => setTab(t.v as Tab)}
        style={{
          fontFamily: "inherit", cursor: "pointer", fontSize: 13,
          fontWeight: active ? 600 : 500,
          color: active ? "#f5f5f7" : "#8a8a92",
          padding: "9px 22px", borderRadius: 12,
          background: active ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.02)",
          border: active ? "1px solid rgba(255,255,255,0.16)" : "1px solid rgba(255,255,255,0.06)",
          boxShadow: active ? "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 14px -6px rgba(0,0,0,0.5)" : "none",
          backdropFilter: "blur(12px)",
          transition: "all 0.18s ease",
        }}
      >
        {t.l}
      </button>
    );
  })}
</div>

        {tab === "hoy" && (
          <>
            {/* Saldo + valor total (primero) */}
            {macro && (
              <div style={{ marginTop: 12, marginBottom: 10, maxWidth: 1500, display: "flex", flexWrap: "wrap", gap: 12 }}>
                <GlowCard glowColor="teal" className="flex-1 min-w-[220px]" padding="14px 20px">
                  <div style={{ color: "var(--text-3)", fontSize: 13, marginBottom: 4 }}>Saldo disponible</div>
                  <div style={{ color: "var(--text)", fontSize: 20, fontWeight: 600 }}>
                    {mostrarMonto(data.saldo_usd ?? 0, divisa, { trm: macro.trm, tasa_eur: macro.tasa_eur })}
                  </div>
                </GlowCard>
                <GlowCard glowColor="blue" className="flex-1 min-w-[220px]" padding="14px 20px">
                  <div style={{ color: "var(--text-3)", fontSize: 13, marginBottom: 4 }}>Valor total</div>
                  <div style={{ color: "var(--text)", fontSize: 20, fontWeight: 600 }}>
                    {mostrarMonto((tiempo_real?.total_valor ?? 0) + (data.saldo_usd ?? 0), divisa, { trm: macro.trm, tasa_eur: macro.tasa_eur })}
                  </div>
                </GlowCard>
              </div>
            )}

            {/* Mis métricas (después) */}
            {tiempo_real && macro && (
              <MisMetricas
                tr={tiempoRealEfectivo ?? tiempo_real}
                divisa={divisa}
                tasas={{ trm: macro.trm, tasa_eur: macro.tasa_eur }}
              />
            )}

            {/* Macro tiles */}
            {macro && <MacroSection macro={macro} />}

            {/* Composition */}
            {Object.keys(composicion).length > 0 && <ComposicionSection composicion={composicion} archivo={archivo} aportes_activos={data.tiempo_real?.posiciones.map(p => p.activo) ?? []} />}

            {/* Real-time positions */}
            {tiempo_real ? <PosicionesSection tr={tiempo_real} divisa={divisa} tasas={{ trm: macro!.trm, tasa_eur: macro!.tasa_eur }} /> : (
              <GlassPanel style={{ padding: 40, textAlign: "center" }}>
                <p style={{ color: "var(--text-3)", marginBottom: 16 }}>Sin inversiones registradas.</p>
                <Link href={`/portafolio/${archivo}/seguimiento`}>
                  <LiquidButton className="text-white font-semibold !px-8 !py-3">Registrar primera inversión</LiquidButton>
                </Link>
              </GlassPanel>
            )}
          </>
        )}

        {tab === "historico" && (
          <HistoricoSection
            historico={historico}
            archivo={archivo}
            composicion={composicion}
            posiciones={tiempo_real?.posiciones ?? []}
            divisa={divisa}
            tasas={macro ? { trm: macro.trm, tasa_eur: macro.tasa_eur } : { trm: 0, tasa_eur: 0 }}
          />
        )}

        {/* Footer */}
        <div style={{ textAlign: "center", marginTop: 32 }}>
          <div style={{ color: "#6e6e73", fontSize: 11, marginBottom: 12 }}>
            Última actualización: <span>{lastUpdate || "—"}</span>
          </div>
          <LiquidButton
            disabled={updating}
            onClick={handleRefresh}
            className="text-white font-semibold !px-8 !py-3"
          >
            {updating ? "Descargando datos..." : "Actualizar datos"}
          </LiquidButton>
        </div>
        <AvisosHost>
          <AvisoSeguimiento archivo={archivo} desviacion={data.desviacion_composicion} />
          {monitorAmbient && (
            <AvisoSenalesMonitor
              archivo={archivo}
              mercadoAbierto={monitorAmbient.mercadoAbierto}
              precios={monitorAmbient.precios}
              rangos={monitorAmbient.rangos}
              monitoreo={monitorAmbient.monitoreo}
            />
          )}
          <AvisoTrm archivo={archivo} trmCambio={macro?.trm_cambio} />
        </AvisosHost>
      </>
  );
}

// ── Nav bar ─────────────────────────────────────────────────

function NavBar({ archivo, active }: { archivo: string; active: string }) {
  const tabs = [
    { id: "dashboard",   href: `/portafolio/${archivo}`,             label: "Dashboard" },
    { id: "analista",    href: `/portafolio/${archivo}/analista`,     label: "Analista" },
    { id: "seguimiento", href: `/portafolio/${archivo}/seguimiento`,  label: "Seguimiento" },
    { id: "bot",         href: `/portafolio/${archivo}/bot`,          label: "Asistente" },
    { id: "monitor",     href: `/portafolio/${archivo}/monitor`,      label: "Monitor" },
    { id: "config",      href: `/portafolio/${archivo}/config`,       label: "Config" },
    { id: "settings",    href: `/settings`,                           label: "Mi Perfil" },
  ];
  return (
    <div style={{ display: "flex", gap: 2, background: "rgba(255,255,255,0.05)", padding: 4, borderRadius: 10 }}>
      {tabs.map(t => (
        <Link key={t.id} href={t.href} style={{
          padding: "7px 16px", borderRadius: 7, fontSize: 12, textDecoration: "none",
          background: active === t.id ? "#1c1c1e" : "transparent",
          color: active === t.id ? "#f5f5f7" : "#6e6e73",
          border: active === t.id ? "1px solid rgba(255,255,255,0.1)" : "none",
        }}>
          {t.label}
        </Link>
      ))}
    </div>
  );
}

// ── Macro section ────────────────────────────────────────────

function MacroSection({ macro }: { macro: NonNullable<DashboardData["macro"]> }) {
  const tiles = [
    { label: "TRM Actual", value: `$${macro.trm.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`, sub: `${macro.trm_cambio > 0 ? "+" : ""}${macro.trm_cambio}% último mes`, subColor: macro.trm_cambio > 0 ? "#30d158" : "#ff453a" },
    { label: "Inflación Colombia", value: `${macro.inf_col}%`, sub: `USA: ${macro.inf_usa}% · Spread: ${macro.spread}%` },
    { label: "Tasa Banrep", value: `${macro.banrep}%`, sub: `CDT ref: ${macro.cdt}%` },
    { label: "Risk Free USA", value: `${macro.risk_free}%`, sub: "Treasury Bills" },
  ];
  return (
    <>
      <SectionTitle>Indicadores Macro</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gridAutoRows: "1fr", gap: 12, marginBottom: 24 }}>
        {tiles.map(t => (
          <GlowCard key={t.label} glowColor="blue" className="flex flex-col h-full">
            <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)", marginBottom: 12 }}>{t.label}</h3>
            <div style={{ fontSize: "2rem", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 4, color: "var(--text)" }}>{t.value}</div>
            <div style={{ fontSize: "0.8rem", color: t.subColor ?? "var(--text-3)" }}>{t.sub}</div>
          </GlowCard>
        ))}
      </div>

      {/* TRM Chart */}
      <TRMChart trm_hist={macro.trm_hist} />
    </>
  );
}

// ── Mis métricas (resumen del portafolio) ────────────────────
function MisMetricas({ tr, divisa, tasas }: {
  tr: NonNullable<DashboardData["tiempo_real"]>;
  divisa: Divisa;
  tasas: { trm: number; tasa_eur: number };
}) {
  const gPos = tr.ganancia_total >= 0;
  const rPos = tr.rentabilidad_total >= 0;

  // Formateadores reusados por AnimatedValue — mismo formato que se usaba antes,
  // solo que ahora se recalculan cada vez que cambia el valor animado.
  const fmtMonto     = (n: number) => mostrarMonto(n, divisa, tasas);
  const fmtGanancia  = (n: number) => `${n >= 0 ? "+" : ""}${mostrarMonto(n, divisa, tasas)}`;
  const fmtRentab    = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;

  const cards: {
    label: string; sub: string; color: string;
    value?: string;
    raw?: number; format?: (n: number) => string;
  }[] = [
    { label: "Invertido",    value: mostrarMonto(tr.total_invertido, divisa, tasas), sub: divisa, color: "#f0f0f3" },
    { label: "Valor hoy",    raw: tr.total_valor,        format: fmtMonto,    sub: divisa, color: "#f0f0f3" },
    { label: "Ganancia",     raw: tr.ganancia_total,     format: fmtGanancia, sub: divisa, color: gPos ? "#30d158" : "#ff453a" },
    { label: "Rentabilidad", raw: tr.rentabilidad_total, format: fmtRentab,   sub: "total", color: rPos ? "#30d158" : "#ff453a" },
  ];

  return (
    <GlassPanel style={{ marginBottom: -1, maxWidth: 1500 }}>
      <div className="metricas-grid" style={{ display: "grid", padding: "10px 12px" }}>
        {cards.map(c => (
          <div key={c.label}>
            <p style={{ fontSize: 12, color: "var(--text-3)", margin: "0 0 7px", textTransform: "uppercase", letterSpacing: "0.06em" }}>{c.label}</p>
            <p style={{ fontSize: 17, fontWeight: 600, margin: 0, color: c.color, letterSpacing: "-0.02em" }}>
              {c.raw !== undefined && c.format
                ? <AnimatedValue value={c.raw} format={c.format} />
                : c.value}
            </p>
            <p style={{ fontSize: 12, color: "var(--text-3)", margin: "6px 0 0" }}>{c.sub}</p>
          </div>
        ))}
      </div>
      <style>{`
        .metricas-grid { grid-template-columns: repeat(4, 1fr); gap: 0; }
        .metricas-grid > div { padding: 6px 16px; border-left: 1px solid rgba(255,255,255,0.07); }
        .metricas-grid > div:first-child { border-left: none; }
        @media (max-width: 640px) {
          .metricas-grid { grid-template-columns: 1fr 1fr; }
          .metricas-grid > div:nth-child(odd)  { border-left: none; }
          .metricas-grid > div:nth-child(even) { border-left: 1px solid rgba(255,255,255,0.07); }
          .metricas-grid > div:nth-child(n+3)  { border-top: 1px solid rgba(255,255,255,0.07); padding-top: 14px; }
        }
      `}</style>
    </GlassPanel>
  );
}

function TickerLogo({ ticker, size = 22 }: { ticker: string; size?: number }) {
  const [err, setErr] = useState(false);
  // "BTC-USD" -> "BTC"; los servicios de acciones no usan el sufijo
  const sym = ticker.split("-")[0].toUpperCase();

  if (err) {
    // Fallback: badge con iniciales y color estable derivado del ticker
    const hue = [...ticker].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
    return (
      <span style={{
        width: size, height: size, borderRadius: 6, flexShrink: 0,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        fontSize: size * 0.4, fontWeight: 700, color: "#fff",
        background: `hsl(${hue}, 45%, 42%)`,
      }}>
        {sym.slice(0, 2)}
      </span>
    );
  }

  return (
    <img
      src={`https://img.logo.dev/ticker/${sym}?token=pk_a7xVdMF8Qlu9rwAfmcdrBQ=${size * 2}&format=png`}
      alt={ticker}
      width={size}
      height={size}
      onError={() => setErr(true)}
      style={{ borderRadius: 6, flexShrink: 0, objectFit: "contain", background: "rgba(255,255,255,0.06)" }}
    />
  );
}


// ── TRM Chart (lazy-loaded Plotly) ───────────────────────────

function TRMChart({ trm_hist }: { trm_hist: { fechas: string[]; valores: number[] } }) {
  const [days, setDays] = useState(90);

  if (!trm_hist || !trm_hist.fechas) return null;

  const n = Math.min(days, trm_hist.fechas.length);
  const fechas = trm_hist.fechas.slice(-n);
  const vals   = trm_hist.valores.slice(-n);
  const ma7 = vals.map((_, i) => i < 6 ? null : vals.slice(i - 6, i + 1).reduce((a, b) => a + b, 0) / 7);

  // Transformar a array de objetos para Recharts
  const data = fechas.map((fecha, i) => ({
    fecha,
    trm: vals[i],
    ma7: ma7[i],
  }));

  const minVal = Math.min(...vals);
  const maxVal = Math.max(...vals);
  const pad = (maxVal - minVal) * 0.1 || 50;

  const fmtFecha = (f: string) => {
    const d = new Date(f);
    return d.toLocaleDateString("es-CO", { day: "2-digit", month: "short" });
  };

  return (
    <GlassPanel>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center" }}>
        <p style={{ color: "var(--text)", fontSize: 14, fontWeight: 600, margin: 0, flex: 1 }}>Tasa Representativa del Mercado (TRM)</p>
        {[7, 30, 60, 90].map(d => (
          <button key={d} onClick={() => setDays(d)}
            style={{ padding: "5px 12px", borderRadius: 7, fontSize: 11, cursor: "pointer", fontFamily: "inherit", border: days === d ? "1px solid rgba(0,113,227,0.5)" : "1px solid var(--glass-border)", background: days === d ? "rgba(0,113,227,0.2)" : "rgba(255,255,255,0.05)", color: days === d ? "#4da3ff" : "var(--text-3)", transition: "all 0.15s" }}>
            {d}d
          </button>
        ))}
      </div>

      <div style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 12, left: 8, bottom: 4 }}>
            <defs>
              <linearGradient id="trmGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0071e3" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#0071e3" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis
              dataKey="fecha"
              tickFormatter={fmtFecha}
              tick={{ fontSize: 11, fill: "var(--text-3)" }}
              stroke="rgba(255,255,255,0.1)"
              minTickGap={40}
            />
            <YAxis
              domain={[minVal - pad, maxVal + pad]}
              tickFormatter={(v) => `$${Math.round(v).toLocaleString("es-CO")}`}
              tick={{ fontSize: 11, fill: "var(--text-3)" }}
              stroke="rgba(255,255,255,0.1)"
              width={70}
            />
            <Tooltip
              contentStyle={{ background: "rgba(12,12,12,0.97)", border: "1px solid var(--glass-border)", borderRadius: 10, fontSize: 12 }}
              labelStyle={{ color: "var(--text)", marginBottom: 4 }}
              labelFormatter={(f) => fmtFecha(f as string)}
              formatter={(value, name) => [
                `$${Math.round(Number(value)).toLocaleString("es-CO")} COP`,
                name === "trm" ? "TRM" : "Media 7d",
              ]}
            />
            <Area type="monotone" dataKey="trm" stroke="#0071e3" strokeWidth={2} fill="url(#trmGradient)" dot={false} />
            <Area type="monotone" dataKey="ma7" stroke="#30d158" strokeWidth={1.5} strokeDasharray="4 3" fill="none" dot={false} connectNulls />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <AnalisisTRM />

      <div style={{ marginTop: 8, fontSize: "0.7rem", color: "var(--text-3)", textAlign: "right" }}>Fuente: Banco de la República</div>
    </GlassPanel>
  );
}

// ── Análisis IA de la TRM (carga aparte, con caché diario) ──
function AnalisisTRM() {
  const [analisis, setAnalisis] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    getTrmAnalisis()
      .then(d => setAnalisis(d.analisis || ""))
      .catch(() => setAnalisis(""))
      .finally(() => setCargando(false));
  }, []);

  // Si no hay análisis y ya cargó, no mostramos nada
  if (!cargando && !analisis) return null;

  return (
    <div style={{ marginTop: 14, padding: "14px 16px", background: "var(--glass)", border: "1px solid var(--glass-border)", borderRadius: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <LogoMark size={20} />
        <span style={{ fontSize: "0.68rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)" }}>Análisis de Atom</span>
      </div>
      {cargando ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#0071e3", animation: "pulse-trm 1.2s infinite" }} />
          <p style={{ fontSize: "0.82rem", color: "var(--text-3)", margin: 0 }}>Analizando el mercado…</p>
          <style>{`@keyframes pulse-trm { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }`}</style>
        </div>
      ) : (
        <p style={{ fontSize: "0.82rem", color: "var(--text-2)", lineHeight: 1.65, margin: 0, whiteSpace: "pre-line" }}>{analisis}</p>
      )}
    </div>
  );
}

// ── Composition section ──────────────────────────────────────

function ComposicionSection({ composicion, archivo, aportes_activos }: { composicion: Record<string, number>; archivo: string; aportes_activos: string[] }) {
  const entrados  = Object.keys(composicion).filter(a => aportes_activos.includes(a));
  const pendientes = Object.keys(composicion).filter(a => !aportes_activos.includes(a));

  return (
    <>
      <SectionTitle>Estado de Entradas</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12, marginBottom: 16, alignItems: "start" }}>
        {[
          { title: "Ya entraste", items: entrados, badge: { bg: "rgba(48,209,88,0.12)", color: "#30d158", border: "rgba(48,209,88,0.2)", label: "ENTRADO" } },
          { title: "Pendientes",  items: pendientes, badge: { bg: "rgba(255,214,10,0.12)", color: "#ffd60a", border: "rgba(255,214,10,0.2)", label: "PENDIENTE" } },
        ].map(({ title, items, badge }) => (
          <GlassPanel key={title} style={{ marginBottom: 0 }}>
            <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "#6e6e73", marginBottom: 12 }}>{title}</h3>
            {items.length === 0
              ? <div style={{ color: title === "Pendientes" ? "#30d158" : "#6e6e73", padding: "8px 0", fontSize: 14 }}>{title === "Pendientes" ? "Ya entraste a todos" : "Sin entradas aún"}</div>
              : items.map(a => (
                <div key={a} style={{ padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <TickerLogo ticker={a} />
                  <span style={{ color: "#f5f5f7" }}>{a}</span>
                  </span>
                  <span style={{ background: badge.bg, color: badge.color, border: `1px solid ${badge.border}`, borderRadius: 980, padding: "3px 10px", fontSize: "0.7rem", fontWeight: 500 }}>{badge.label}</span>
                </div>
              ))}
          </GlassPanel>
        ))}
      </div>
    </>
  );
}

// ── Positions table ──────────────────────────────────────────

function PosicionesSection({ tr, divisa, tasas }: {
  tr: NonNullable<DashboardData["tiempo_real"]>;
  divisa: Divisa;
  tasas: { trm: number; tasa_eur: number };
}) {
  const gc = tr.ganancia_total > 0 ? "#30d158" : "#ff453a";
  const fmtCop = (v: number | null, signo = false) =>
    v == null ? "—" : `${signo && v > 0 ? "+" : ""}$${v.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`;
  return (
    <>
      <SectionTitle>Portafolio en Tiempo Real</SectionTitle>
      <GlassPanel style={{ textAlign: "center" }}>
        <div style={{ color: "var(--text-3)", fontSize: "0.85rem", marginBottom: 8 }}>Ganancia Total</div>
        <div style={{ fontSize: "3rem", fontWeight: 600, letterSpacing: "-0.04em", color: gc, lineHeight: 1 }}>
          {tr.ganancia_total > 0 ? "+" : ""}{mostrarMonto(tr.ganancia_total, divisa, tasas)}
        </div>
        <div style={{ marginTop: 12, color: "#6e6e73", fontSize: "0.85rem" }}>
          Invertido: <strong style={{ color: "#f5f5f7" }}>{mostrarMonto(tr.total_invertido, divisa, tasas)}</strong>
          {" → "}Hoy: <strong style={{ color: "#f5f5f7" }}>{mostrarMonto(tr.total_valor, divisa, tasas)}</strong>
          {" "}<span style={{ color: gc }}>({tr.rentabilidad_total > 0 ? "+" : ""}{tr.rentabilidad_total}%)</span>
        </div>
        {divisa === "COP" && (tr.fx_cop_total != null || tr.inflacion_cop_total != null) && (
          <div style={{ marginTop: 6, color: "#6e6e73", fontSize: "0.78rem" }}>
            Dif. cambio: <strong style={{ color: (tr.fx_cop_total ?? 0) >= 0 ? "#30d158" : "#ff453a" }}>{fmtCop(tr.fx_cop_total, true)}</strong>
            {"  ·  "}Inflación: <strong style={{ color: "#ff9f0a" }}>−${(tr.inflacion_cop_total ?? 0).toLocaleString("es-CO", { maximumFractionDigits: 0 })}</strong>
            {"  (COP)"}
          </div>
        )}
      </GlassPanel>
      <GlassPanel style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Activo", "Precio hoy", "Fracciones", "Valor", "Ganancia", "Rentabilidad", ...(divisa === "COP" ? ["Dif. cambio", "Inflación"] : [])].map(h => (
                <th key={h} style={{ fontSize: "0.7rem", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase", color: "#6e6e73", padding: "10px 16px", textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tr.posiciones.map(p => {
              const c = p.ganancia > 0 ? "#30d158" : "#ff453a";
              return (
                <tr key={p.activo}>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem" }}>
                    <strong style={{ color: "#f5f5f7" }}>{p.activo}</strong>
                  </td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>
                    ${p.precio_hoy.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>
                    {p.fracciones}
                  </td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>
                    {mostrarMonto(p.valor_hoy, divisa, tasas)}
                  </td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: c, fontWeight: 500 }}>
                    {p.ganancia > 0 ? "+" : ""}{mostrarMonto(p.ganancia, divisa, tasas)}
                  </td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: c, fontWeight: 500 }}>
                    {p.rentabilidad > 0 ? "+" : ""}{p.rentabilidad}%
                  </td>
                  {divisa === "COP" && (<>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: (p.fx_cop ?? 0) >= 0 ? "#30d158" : "#ff453a" }}>
                    {fmtCop(p.fx_cop, true)}
                  </td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#ff9f0a" }}>
                    {p.inflacion_cop == null ? "—" : `−$${p.inflacion_cop.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`}
                  </td>
                  </>)}               
                </tr>
              );
            })}
          </tbody>
        </table>
      </GlassPanel>
    </>
  );
}

// ── Historical section ───────────────────────────────────────

const RANGOS_HISTORICO = [
  { v: 7,      l: "7D" },
  { v: 30,     l: "30D" },
  { v: 90,     l: "90D" },
  { v: 365,    l: "1A" },
  { v: "todo", l: "Todo" },
] as const;
type RangoHistorico = typeof RANGOS_HISTORICO[number]["v"];

function HistoricoSection({ historico, archivo, composicion, posiciones, divisa, tasas }: {
  historico:   DashboardData["historico"];
  archivo:     string;
  composicion: Record<string, number>;
  posiciones:  Posicion[];
  divisa:      Divisa;
  tasas:       { trm: number; tasa_eur: number };
}) {
  const [rango, setRango] = useState<RangoHistorico>(90);

  if (!historico || !historico.length) return (
    <GlassPanel>
      <p style={{ color: "var(--text-3)", textAlign: "center" }}>Aún no hay registros históricos. El sistema guarda uno automáticamente cada día.</p>
    </GlassPanel>
  );

  const n = rango === "todo" ? historico.length : Math.min(rango, historico.length);
  const filtrado = historico.slice(-n);
  const desde = filtrado[0].fecha;

  const hitos = calcularHitos(filtrado);
  // El timeline de entradas NO se filtra por rango a proposito: es la
  // narrativa de como se construyo el portafolio desde el inicio, no una
  // metrica de tendencia reciente -- filtrarla escondería las entradas mas
  // antiguas (justamente las mas relevantes para esa narrativa) apenas el
  // usuario mira un rango corto.
  const pendientes = Object.keys(composicion).filter(a => !posiciones.some(p => p.activo === a));

  return (
    <>
      {/* Selector de rango — controla hitos, gráfico, timeline y tabla a la vez */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {RANGOS_HISTORICO.map(r => (
          <button key={r.l} onClick={() => setRango(r.v)}
            style={{ padding: "6px 14px", borderRadius: 8, fontSize: 12, cursor: "pointer", fontFamily: "inherit",
              border: rango === r.v ? "1px solid rgba(0,113,227,0.5)" : "1px solid var(--glass-border)",
              background: rango === r.v ? "rgba(0,113,227,0.2)" : "rgba(255,255,255,0.05)",
              color: rango === r.v ? "#4da3ff" : "var(--text-3)", transition: "all 0.15s" }}>
            {r.l}
          </button>
        ))}
      </div>

      {hitos && <HitosHistoricos hitos={hitos} divisa={divisa} tasas={tasas} />}

      <GraficoHistorico historico={filtrado} divisa={divisa} tasas={tasas} mejorFecha={hitos?.mejor.fecha} peorFecha={hitos?.peor.fecha} />

      <AnalisisHistorico archivo={archivo} />

      <TimelineEntradas posiciones={posiciones} pendientes={pendientes} divisa={divisa} tasas={tasas} />

      <SectionTitle>Evolución por Snapshot</SectionTitle>
      <GlassPanel style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Fecha","TRM","Valor","Ganancia","Rentabilidad"].map(h => (
                <th key={h} style={{ fontSize: "0.7rem", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase", color: "#6e6e73", padding: "10px 16px", textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...filtrado].reverse().map(r => {
              const g = r.resumen.ganancia_total; const rv = r.resumen.rentabilidad_total;
              const c = g > 0 ? "#30d158" : "#ff453a";
              return (
                <tr key={r.fecha}>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>{r.fecha}</td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>{r.macro ? `$${r.macro.trm.toLocaleString("es-CO", { maximumFractionDigits: 0 })}` : "—"}</td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>{mostrarMonto(r.resumen.total_valor, divisa, tasas)}</td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: c, fontWeight: 500 }}>{g > 0 ? "+" : ""}{mostrarMonto(g, divisa, tasas)}</td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: c, fontWeight: 500 }}>{rv > 0 ? "+" : ""}{rv}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </GlassPanel>
    </>
  );
}

// ── Hitos: mejor/peor día, racha, rentabilidad acumulada del rango ──

interface Hitos {
  mejor: { fecha: string; valorUsd: number };
  peor:  { fecha: string; valorUsd: number };
  racha: number;
  rentAcumuladaPct: number;
}

function calcularHitos(filtrado: DashboardData["historico"]): Hitos | null {
  if (filtrado.length < 2) return null;
  const deltas = filtrado.slice(1).map((r, i) => ({
    fecha: r.fecha,
    valorUsd: r.resumen.total_valor - filtrado[i].resumen.total_valor,
  }));
  const mejor = deltas.reduce((a, b) => (b.valorUsd > a.valorUsd ? b : a));
  const peor  = deltas.reduce((a, b) => (b.valorUsd < a.valorUsd ? b : a));
  let racha = 0;
  for (let i = deltas.length - 1; i >= 0; i--) {
    if (deltas[i].valorUsd > 0) racha++; else break;
  }
  const primero = filtrado[0].resumen.total_valor;
  const ultimo  = filtrado[filtrado.length - 1].resumen.total_valor;
  const rentAcumuladaPct = primero !== 0 ? ((ultimo - primero) / primero) * 100 : 0;
  return { mejor, peor, racha, rentAcumuladaPct };
}

function HitosHistoricos({ hitos, divisa, tasas }: { hitos: Hitos; divisa: Divisa; tasas: { trm: number; tasa_eur: number } }) {
  const cards = [
    { label: "Mejor día", value: mostrarMonto(hitos.mejor.valorUsd, divisa, tasas), sub: hitos.mejor.fecha, color: "#30d158" },
    { label: "Peor día",  value: mostrarMonto(hitos.peor.valorUsd, divisa, tasas),  sub: hitos.peor.fecha,  color: "#ff453a" },
    { label: "Racha actual", value: `${hitos.racha} ${hitos.racha === 1 ? "día" : "días"}`, sub: hitos.racha > 0 ? "ganando consecutivos" : "sin racha activa", color: hitos.racha > 0 ? "#30d158" : "var(--text-3)" },
    { label: "Rentabilidad acum.", value: `${hitos.rentAcumuladaPct > 0 ? "+" : ""}${hitos.rentAcumuladaPct.toFixed(2)}%`, sub: "en el rango seleccionado", color: hitos.rentAcumuladaPct >= 0 ? "#30d158" : "#ff453a" },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 24 }}>
      {cards.map(c => (
        <GlowCard key={c.label} glowColor="blue" className="flex flex-col justify-between">
          <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)", marginBottom: 12 }}>{c.label}</h3>
          <div style={{ fontSize: "1.7rem", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 4, color: c.color }}>{c.value}</div>
          <div style={{ fontSize: "0.8rem", color: "var(--text-3)" }}>{c.sub}</div>
        </GlowCard>
      ))}
    </div>
  );
}

// ── Gráfico: invertido vs valor real, con marcadores en mejor/peor día ──

function GraficoHistorico({ historico, divisa, tasas, mejorFecha, peorFecha }: {
  historico: DashboardData["historico"];
  divisa: Divisa;
  tasas: { trm: number; tasa_eur: number };
  mejorFecha?: string;
  peorFecha?: string;
}) {
  const factor = divisa === "COP" ? tasas.trm : divisa === "EUR" ? tasas.tasa_eur : 1;
  const data = historico.map(r => ({
    fecha: r.fecha,
    real: r.resumen.total_valor * factor,
    invertido: r.resumen.total_invertido * factor,
    esMejor: r.fecha === mejorFecha,
    esPeor: r.fecha === peorFecha,
  }));

  const fmtFecha = (f: string) => new Date(f).toLocaleDateString("es-CO", { day: "2-digit", month: "short" });
  const fmtMonto = (v: number) => mostrarMonto(v / factor, divisa, tasas);

  return (
    <GlassPanel>
      <p style={{ color: "var(--text)", fontSize: 14, fontWeight: 600, margin: "0 0 12px" }}>Valor del portafolio en el tiempo</p>
      <div style={{ display: "flex", gap: 14, marginBottom: 10, fontSize: 11, color: "var(--text-3)" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><i style={{ width: 8, height: 8, borderRadius: "50%", background: "#30d158", display: "inline-block" }} />Valor real</span>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><i style={{ width: 8, height: 8, borderRadius: "50%", background: "#6e6e73", display: "inline-block" }} />Invertido</span>
      </div>
      <div style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 12, left: 8, bottom: 4 }}>
            <defs>
              <linearGradient id="historicoGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#30d158" stopOpacity={0.28} />
                <stop offset="100%" stopColor="#30d158" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis dataKey="fecha" tickFormatter={fmtFecha} tick={{ fontSize: 11, fill: "var(--text-3)" }} stroke="rgba(255,255,255,0.1)" minTickGap={40} />
            <YAxis tickFormatter={(v) => fmtMonto(v)} tick={{ fontSize: 11, fill: "var(--text-3)" }} stroke="rgba(255,255,255,0.1)" width={80} />
            <Tooltip
              contentStyle={{ background: "rgba(12,12,12,0.97)", border: "1px solid var(--glass-border)", borderRadius: 10, fontSize: 12 }}
              labelStyle={{ color: "var(--text)", marginBottom: 4 }}
              labelFormatter={(f) => fmtFecha(f as string)}
              formatter={(value, name) => [fmtMonto(Number(value)), name === "real" ? "Valor real" : "Invertido"]}
            />
            <Area type="monotone" dataKey="invertido" stroke="#6e6e73" strokeWidth={1.5} strokeDasharray="4 3" fill="none" dot={false} />
            <Area type="monotone" dataKey="real" stroke="#30d158" strokeWidth={2} fill="url(#historicoGradient)"
              dot={(props: { cx?: number; cy?: number; payload?: { esMejor?: boolean; esPeor?: boolean } }) => {
                const { cx, cy, payload } = props;
                if (!payload?.esMejor && !payload?.esPeor) return <g key={`dot-${cx}-${cy}`} />;
                return <circle key={`dot-${cx}-${cy}`} cx={cx} cy={cy} r={4.5} fill={payload.esMejor ? "#30d158" : "#ff453a"} stroke="#0a0a0b" strokeWidth={1.5} />;
              }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </GlassPanel>
  );
}

// ── Análisis IA del histórico (mismo patrón que AnalisisTRM, cache diario por portafolio) ──

function AnalisisHistorico({ archivo }: { archivo: string }) {
  const [analisis, setAnalisis] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    getHistoricoAnalisis(archivo)
      .then(d => setAnalisis(d.analisis || ""))
      .catch(() => setAnalisis(""))
      .finally(() => setCargando(false));
  }, [archivo]);

  if (!cargando && !analisis) return null;

  return (
    <GlassPanel>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <LogoMark size={20} />
        <span style={{ fontSize: "0.68rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)" }}>Análisis de Atom — Histórico</span>
      </div>
      {cargando ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#0071e3", animation: "pulse-hist 1.2s infinite" }} />
          <p style={{ fontSize: "0.82rem", color: "var(--text-3)", margin: 0 }}>Analizando tu trayectoria…</p>
          <style>{`@keyframes pulse-hist { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }`}</style>
        </div>
      ) : (
        <p style={{ fontSize: "0.82rem", color: "var(--text-2)", lineHeight: 1.65, margin: 0, whiteSpace: "pre-line" }}>{analisis}</p>
      )}
    </GlassPanel>
  );
}

// ── Historial de entradas: línea de tiempo cronológica ──

function TimelineEntradas({ posiciones, pendientes, divisa, tasas }: {
  posiciones: Posicion[];
  pendientes: string[];
  divisa: Divisa;
  tasas: { trm: number; tasa_eur: number };
}) {
  const ordenadas = [...posiciones].sort((a, b) => a.fecha_inicio.localeCompare(b.fecha_inicio));
  if (!ordenadas.length && !pendientes.length) return null;

  return (
    <>
      <SectionTitle>Historial de Entradas</SectionTitle>
      <GlassPanel style={{ padding: "4px 20px" }}>
        {ordenadas.map(p => {
          const ganando = p.rentabilidad >= 0;
          return (
            <div key={p.activo} style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              <TickerLogo ticker={p.activo} size={34} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{p.activo}</div>
                <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>Entró el {p.fecha_inicio} · {mostrarMonto(p.invertido / p.fracciones, divisa, tasas)} promedio</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: ganando ? "#30d158" : "#ff453a" }}>{p.rentabilidad > 0 ? "+" : ""}{p.rentabilidad}%</div>
                <div style={{ fontSize: 11, color: "var(--text-3)" }}>desde entrada</div>
              </div>
              <span style={{
                background: ganando ? "rgba(48,209,88,0.12)" : "rgba(255,69,58,0.12)",
                color: ganando ? "#30d158" : "#ff453a",
                border: `1px solid ${ganando ? "rgba(48,209,88,0.2)" : "rgba(255,69,58,0.2)"}`,
                borderRadius: 980, padding: "3px 10px", fontSize: "0.7rem", fontWeight: 500,
              }}>{ganando ? "GANANDO" : "PERDIENDO"}</span>
            </div>
          );
        })}
        {pendientes.map(a => (
          <div key={a} style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <TickerLogo ticker={a} size={34} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{a}</div>
              <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>Parte de la meta — aún no ejecutado</div>
            </div>
            <div style={{ textAlign: "right", fontSize: 13, color: "var(--text-3)" }}>—</div>
            <span style={{ background: "rgba(255,214,10,0.12)", color: "#ffd60a", border: "1px solid rgba(255,214,10,0.2)", borderRadius: 980, padding: "3px 10px", fontSize: "0.7rem", fontWeight: 500 }}>PENDIENTE</span>
          </div>
        ))}
      </GlassPanel>
    </>
  );
}
