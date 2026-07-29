"use client";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { MagneticTabs } from "@/components/ui/magnetic-tabs";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { GlassPanel } from "@/components/ui/glass-panel";
import { GlowCard } from "@/components/ui/spotlight-card";
import { GlassBackground } from "@/components/ui/glass-background";
import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { LogoMark } from "@/components/ui/logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionTitle } from "@/components/ui/card";
import { authMe, authLogout, triggerRecolector, getUltimaActualizacion, type DashboardData } from "@/lib/api";
import { getDashboard, getTrmAnalisis } from "@/lib/api";
import { style } from "framer-motion/client";
import { PageIntro } from "@/components/ui/page-intro";
import {getConfig} from "@/lib/api";
import { mostrarMonto, type Divisa } from "@/lib/divisas";

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

  const load = useCallback(async () => {
    try {
      const me = await authMe();
      if (!me.authenticated) { router.push("/login"); return; }
      setUsername(me.username);
      const d = await getDashboard(archivo);
      setData(d);
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

  useEffect(() => { load(); }, [load]);

  async function handleLogout() {
    await authLogout();
    router.push("/login");
  }

  async function handleRefresh() {
    setUpdating(true);
    try {
      await triggerRecolector();
      await load();
    } finally {
      setUpdating(false);
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
            {/* Mis métricas */}
            {tiempo_real && macro && (
         <MisMetricas
         tr={tiempo_real}
         divisa={divisa}
         tasas={{ trm: macro.trm, tasa_eur: macro.tasa_eur }}
  />
)}

            {/* Macro tiles */}
            {macro && <MacroSection macro={macro} />}

            {/* Composition */}
            {Object.keys(composicion).length > 0 && <ComposicionSection composicion={composicion} archivo={archivo} aportes_activos={data.tiempo_real?.posiciones.map(p => p.activo) ?? []} />}

            {/* Real-time positions */}
            {tiempo_real ? <PosicionesSection tr={tiempo_real} /> : (
              <GlassPanel style={{ padding: 40, textAlign: "center" }}>
                <p style={{ color: "var(--text-3)", marginBottom: 16 }}>Sin inversiones registradas.</p>
                <Link href={`/portafolio/${archivo}/seguimiento`}>
                  <LiquidButton className="text-white font-semibold !px-8 !py-3">Registrar primera inversión</LiquidButton>
                </Link>
              </GlassPanel>
            )}
          </>
        )}

        {tab === "historico" && <HistoricoSection historico={historico} />}

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
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 24 }}>
        {tiles.map(t => (
          <GlowCard key={t.label} glowColor="blue" className="flex flex-col justify-between" >
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

  const cards = [
    { label: "Invertido",    value: mostrarMonto(tr.total_invertido, divisa, tasas), sub: divisa, color: "#f0f0f3" },
    { label: "Valor hoy",    value: mostrarMonto(tr.total_valor, divisa, tasas),     sub: divisa, color: "#f0f0f3" },
    { label: "Ganancia",     value: `${gPos ? "+" : ""}${mostrarMonto(tr.ganancia_total, divisa, tasas)}`, sub: divisa, color: gPos ? "#30d158" : "#ff453a" },
    { label: "Rentabilidad", value: `${rPos ? "+" : ""}${tr.rentabilidad_total.toFixed(1)}%`, sub: "total", color: rPos ? "#30d158" : "#ff453a" },
  ];

  return (
    <GlassPanel style={{ marginBottom: -1, maxWidth: 1500 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", padding: "0px 20px" }}>
        {cards.map((c, i) => (
          <div key={c.label} style={{ padding: "0 10px", borderLeft: i === 0 ? "none" : "1px solid rgba(255,255,255,0.07)" }}>
            <p style={{ fontSize: 12, color: "var(--text-3)", margin: "0 0 7px", textTransform: "uppercase", letterSpacing: "0.06em" }}>{c.label}</p>
            <p style={{ fontSize: 17, fontWeight: 600, margin: 0, color: c.color, letterSpacing: "-0.02em" }}>{c.value}</p>
            <p style={{ fontSize: 12, color: "var(--text-3)", margin: "6px 0 0" }}>{c.sub}</p>
          </div>
        ))}
      </div>
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
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
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

function PosicionesSection({ tr }: { tr: NonNullable<DashboardData["tiempo_real"]> }) {
  const gc = tr.ganancia_total > 0 ? "#30d158" : "#ff453a";
  return (
    <>
      <SectionTitle>Portafolio en Tiempo Real</SectionTitle>
      <GlassPanel style={{ textAlign: "center" }}>
        <div style={{ color: "var(--text-3)", fontSize: "0.85rem", marginBottom: 8 }}>Ganancia Real Total (pesos de hoy)</div>
        <div style={{ fontSize: "3rem", fontWeight: 600, letterSpacing: "-0.04em", color: gc, lineHeight: 1 }}>
          {tr.ganancia_total > 0 ? "+" : ""}${tr.ganancia_total.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
        </div>
        <div style={{ marginTop: 12, color: "#6e6e73", fontSize: "0.85rem" }}>
          Invertido: <strong style={{ color: "#f5f5f7" }}>${tr.total_invertido.toLocaleString("es-CO", { maximumFractionDigits: 0 })}</strong>
          {" → "}Hoy: <strong style={{ color: "#f5f5f7" }}>${tr.total_valor.toLocaleString("es-CO", { maximumFractionDigits: 0 })}</strong>
          {" "}<span style={{ color: gc }}>({tr.rentabilidad_total > 0 ? "+" : ""}{tr.rentabilidad_total}%)</span>
        </div>
      </GlassPanel>
      <GlassPanel style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Activo", "Precio hoy", "Fracciones", "Valor COP", "Ganancia", "Rentabilidad"].map(h => (
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
                    ${p.valor_hoy.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
                  </td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: c, fontWeight: 500 }}>
                    {p.ganancia > 0 ? "+" : ""}${p.ganancia.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
                  </td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: c, fontWeight: 500 }}>
                    {p.rentabilidad > 0 ? "+" : ""}{p.rentabilidad}%
                  </td>
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

function HistoricoSection({ historico }: { historico: DashboardData["historico"] }) {
  if (!historico || !historico.length) return (
    <GlassPanel>
      <p style={{ color: "var(--text-3)", textAlign: "center" }}>Aún no hay registros históricos. El sistema guardará uno automáticamente cada día.</p>
    </GlassPanel>
  );
  const ul  = historico[historico.length - 1];
  const pr  = historico[0];
  const gac = ul.resumen.ganancia_total;
  const rac = ul.resumen.rentabilidad_total;
  return (
    <>
      <SectionTitle>Resumen Acumulado</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 24 }}>
        {[
          { label: "Días registrados", value: historico.length, sub: `desde ${pr.fecha}` },
          { label: "Valor actual",     value: `$${ul.resumen.total_valor.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`, sub: "COP", color: "#30d158" },
          { label: "Ganancia acumulada", value: `${gac > 0 ? "+" : ""}$${gac.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`, sub: "COP real", color: gac > 0 ? "#30d158" : "#ff453a" },
          { label: "Rentabilidad total", value: `${rac > 0 ? "+" : ""}${rac}%`, sub: "desde inicio", color: rac > 0 ? "#30d158" : "#ff453a" },
        ].map(t => (
          <GlowCard key={t.label} glowColor="blue" className="flex flex-col justify-between">
            <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)", marginBottom: 12 }}>{t.label}</h3>
            <div style={{ fontSize: "2rem", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 4, color: (t as { color?: string }).color ?? "var(--text)" }}>{t.value}</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-3)" }}>{t.sub}</div>
          </GlowCard>
        ))}
      </div>
      <SectionTitle>Registro Diario</SectionTitle>
      <GlassPanel style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Fecha","TRM","Valor COP","Ganancia","Rentabilidad"].map(h => (
                <th key={h} style={{ fontSize: "0.7rem", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase", color: "#6e6e73", padding: "10px 16px", textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...historico].reverse().map(r => {
              const g = r.resumen.ganancia_total; const rv = r.resumen.rentabilidad_total;
              const c = g > 0 ? "#30d158" : "#ff453a";
              return (
                <tr key={r.fecha}>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>{r.fecha}</td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>${r.macro.trm.toLocaleString("es-CO", { maximumFractionDigits: 0 })}</td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: "#a1a1a6" }}>${r.resumen.total_valor.toLocaleString("es-CO", { maximumFractionDigits: 0 })}</td>
                  <td style={{ padding: "14px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: "0.875rem", color: c, fontWeight: 500 }}>{g > 0 ? "+" : ""}${g.toLocaleString("es-CO", { maximumFractionDigits: 0 })}</td>
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
