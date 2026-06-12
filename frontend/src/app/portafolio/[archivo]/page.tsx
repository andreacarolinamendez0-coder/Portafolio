"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { LogoMark } from "@/components/ui/logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionTitle } from "@/components/ui/card";
import { authMe, authLogout, getDashboard, triggerRecolector, getUltimaActualizacion, type DashboardData } from "@/lib/api";

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

  const load = useCallback(async () => {
    try {
      const me = await authMe();
      if (!me.authenticated) { router.push("/login"); return; }
      setUsername(me.username);
      const d = await getDashboard(archivo);
      setData(d);
      const { timestamp } = await getUltimaActualizacion();
      setLastUpdate(timestamp);
    } catch {
      router.push("/portafolios");
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
    <div className="min-h-screen flex items-center justify-center" style={{ background: "#000" }}>
      <div style={{ color: "#6e6e73", fontSize: 14 }}>Cargando portafolio...</div>
    </div>
  );

  const { portafolio, composicion, tiempo_real, historico, macro } = data;
  const perfil = portafolio.perfil;
  const gc     = tiempo_real && tiempo_real.ganancia_total > 0 ? "#30d158" : "#ff453a";

  return (
    <div style={{ background: "#000", minHeight: "100vh", color: "#f5f5f7" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 24px 48px" }}>

        {/* Portfolio header card */}
        <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "16px 24px", marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <LogoMark size={42} />
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <h1 style={{ color: "#f5f5f7", fontSize: 17, fontWeight: 600, letterSpacing: "-0.02em", margin: 0 }}>
                    {portafolio.nombre}
                  </h1>
                  <Badge variant="outline" style={perfil === "agresivo"
                    ? { background: "rgba(255,214,10,0.12)", color: "#ffd60a", border: "1px solid rgba(255,214,10,0.2)", fontSize: "0.65rem" }
                    : { background: "rgba(0,113,227,0.12)", color: "#4da3ff", border: "1px solid rgba(0,113,227,0.2)", fontSize: "0.65rem" }}>
                    {perfil.toUpperCase()}
                  </Badge>
                </div>
                <p style={{ color: "#6e6e73", fontSize: 12, margin: "2px 0 0" }}>
                  {portafolio.propietario} · Desde {portafolio.fecha_inicio}
                </p>
              </div>
            </div>
            <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
              {tiempo_real && (
                <>
                  <div style={{ textAlign: "right" }}>
                    <p style={{ color: "#6e6e73", fontSize: 10, margin: 0, letterSpacing: "0.04em", textTransform: "uppercase" }}>Valor hoy</p>
                    <p style={{ color: gc, fontSize: 15, fontWeight: 600, margin: 0, letterSpacing: "-0.02em" }}>
                      ${tiempo_real.total_valor.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
                    </p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <p style={{ color: "#6e6e73", fontSize: 10, margin: 0, letterSpacing: "0.04em", textTransform: "uppercase" }}>Ganancia</p>
                    <p style={{ color: gc, fontSize: 15, fontWeight: 600, margin: 0 }}>
                      {tiempo_real.rentabilidad_total > 0 ? "+" : ""}{tiempo_real.rentabilidad_total}%
                    </p>
                  </div>
                </>
              )}
              <button onClick={handleLogout} style={{ background: "none", border: "none", color: "#6e6e73", fontSize: 12, cursor: "pointer" }}>
                Salir
              </button>
            </div>
          </div>

          {/* Nav */}
          <NavBar archivo={archivo} active="dashboard" />
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 2, marginBottom: 28, background: "#111", padding: 4, borderRadius: 12, border: "1px solid rgba(255,255,255,0.08)", width: "fit-content" }}>
          {(["hoy", "historico"] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ padding: "8px 22px", borderRadius: 8, cursor: "pointer", fontSize: "0.875rem", fontWeight: tab === t ? 500 : 400, color: tab === t ? "#f5f5f7" : "#6e6e73", border: tab === t ? "1px solid rgba(255,255,255,0.08)" : "none", background: tab === t ? "#1a1a1a" : "transparent", transition: "all 0.15s", fontFamily: "inherit" }}>
              {t === "hoy" ? "Hoy" : "Histórico"}
            </button>
          ))}
        </div>

        {tab === "hoy" && (
          <>
            {/* Macro tiles */}
            {macro && <MacroSection macro={macro} />}

            {/* Composition */}
            {Object.keys(composicion).length > 0 && <ComposicionSection composicion={composicion} archivo={archivo} aportes_activos={data.tiempo_real?.posiciones.map(p => p.activo) ?? []} />}

            {/* Real-time positions */}
            {tiempo_real ? <PosicionesSection tr={tiempo_real} /> : (
              <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 40, textAlign: "center", marginBottom: 16 }}>
                <p style={{ color: "#6e6e73", marginBottom: 16 }}>Sin inversiones registradas.</p>
                <Link href={`/portafolio/${archivo}/seguimiento`}>
                  <Button style={{ background: "#0071e3", color: "#fff", borderRadius: 980 }}>Registrar primera inversión</Button>
                </Link>
              </div>
            )}
          </>
        )}

        {tab === "historico" && <HistoricoSection historico={historico} />}

        {/* Footer */}
        <div style={{ textAlign: "center", marginTop: 32 }}>
          <div style={{ color: "#6e6e73", fontSize: 11, marginBottom: 12 }}>
            Última actualización: <span>{lastUpdate || "—"}</span>
          </div>
          <Button
            variant="outline"
            disabled={updating}
            onClick={handleRefresh}
            style={{ background: "rgba(255,255,255,0.05)", color: "#a1a1a6", border: "1px solid rgba(255,255,255,0.08)", padding: "10px 28px", borderRadius: 980, fontSize: 13 }}
          >
            {updating ? "⏳ Descargando datos..." : "Actualizar datos"}
          </Button>
        </div>
      </div>
    </div>
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
      <Link href="/portafolios" style={{ marginLeft: "auto", padding: "7px 12px", fontSize: 12, textDecoration: "none", color: "#6e6e73" }}>
        ← Portafolios
      </Link>
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
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 16 }}>
        {tiles.map(t => (
          <div key={t.label} style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24 }}>
            <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "#6e6e73", marginBottom: 12 }}>{t.label}</h3>
            <div style={{ fontSize: "2rem", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 4, color: "#f5f5f7" }}>{t.value}</div>
            <div style={{ fontSize: "0.8rem", color: t.subColor ?? "#6e6e73" }}>{t.sub}</div>
          </div>
        ))}
      </div>

      {/* TRM Chart */}
      <TRMChart trm_hist={macro.trm_hist} />
    </>
  );
}

// ── TRM Chart (lazy-loaded Plotly) ───────────────────────────

function TRMChart({ trm_hist }: { trm_hist: { fechas: string[]; valores: number[] } }) {
  const [days, setDays] = useState(90);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const load = async () => {
      const Plotly = (await import("plotly.js-dist-min" as never)) as typeof import("plotly.js");
      const n = Math.min(days, trm_hist.fechas.length);
      const fechas = trm_hist.fechas.slice(-n);
      const vals   = trm_hist.valores.slice(-n);
      const ma7: (number | null)[] = vals.map((_, i) => i < 6 ? null : vals.slice(i - 6, i + 1).reduce((a, b) => a + b, 0) / 7);

      Plotly.react("trm-chart", [
        { x: fechas, y: vals, type: "scatter", mode: "lines", line: { color: "#0071e3", width: 2 }, hovertemplate: "<b>$%{y:,.0f} COP/USD</b><br>%{x}<extra>TRM</extra>" },
        { x: fechas, y: ma7, type: "scatter", mode: "lines", line: { color: "#30d158", width: 1.5, dash: "dot" }, opacity: 0.8, hovertemplate: "<b>$%{y:,.0f}</b><extra>Media 7d</extra>" },
      ] as Plotly.Data[], {
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(17,17,17,0.6)",
        margin: { l: 80, r: 16, t: 8, b: 36 }, showlegend: false, hovermode: "x unified",
        hoverlabel: { bgcolor: "rgba(12,12,12,0.97)", bordercolor: "rgba(255,255,255,0.1)", font: { size: 12, color: "#f5f5f7" } },
        xaxis: { gridcolor: "rgba(255,255,255,0.05)", color: "#6e6e73", tickfont: { size: 11, color: "#6e6e73" } },
        yaxis: { gridcolor: "rgba(255,255,255,0.05)", color: "#6e6e73", tickfont: { size: 11, color: "#6e6e73" }, tickformat: "$,.0f", ticksuffix: " COP", range: [3000, Math.max(...vals) * 1.05] },
      } as Plotly.Layout, { responsive: true, displayModeBar: false });
    };
    load();
  }, [days, trm_hist]);

  return (
    <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24, marginBottom: 16 }}>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center" }}>
        <p style={{ color: "#f5f5f7", fontSize: 14, fontWeight: 600, margin: 0, flex: 1 }}>Tasa Representativa del Mercado (TRM)</p>
        {[7, 30, 60, 90].map(d => (
          <button key={d} onClick={() => setDays(d)}
            style={{ padding: "5px 12px", borderRadius: 7, fontSize: 11, cursor: "pointer", fontFamily: "inherit", border: days === d ? "1px solid rgba(0,113,227,0.5)" : "1px solid rgba(255,255,255,0.08)", background: days === d ? "rgba(0,113,227,0.2)" : "rgba(255,255,255,0.05)", color: days === d ? "#4da3ff" : "#6e6e73", transition: "all 0.15s" }}>
            {d}d
          </button>
        ))}
      </div>
      <div id="trm-chart" style={{ width: "100%", height: 240 }} />
      <div style={{ marginTop: 8, fontSize: "0.7rem", color: "#6e6e73", textAlign: "right" }}>Fuente: Banco de la República</div>
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
          <div key={title} style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24 }}>
            <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "#6e6e73", marginBottom: 12 }}>{title}</h3>
            {items.length === 0
              ? <div style={{ color: title === "Pendientes" ? "#30d158" : "#6e6e73", padding: "8px 0", fontSize: 14 }}>{title === "Pendientes" ? "Ya entraste a todos" : "Sin entradas aún"}</div>
              : items.map(a => (
                <div key={a} style={{ padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ color: "#f5f5f7" }}>{a}</span>
                  <span style={{ background: badge.bg, color: badge.color, border: `1px solid ${badge.border}`, borderRadius: 980, padding: "3px 10px", fontSize: "0.7rem", fontWeight: 500 }}>{badge.label}</span>
                </div>
              ))}
          </div>
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
      <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24, marginBottom: 16, textAlign: "center" }}>
        <div style={{ color: "#6e6e73", fontSize: "0.85rem", marginBottom: 8 }}>Ganancia Real Total (pesos de hoy)</div>
        <div style={{ fontSize: "3rem", fontWeight: 600, letterSpacing: "-0.04em", color: gc, lineHeight: 1 }}>
          {tr.ganancia_total > 0 ? "+" : ""}${tr.ganancia_total.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
        </div>
        <div style={{ marginTop: 12, color: "#6e6e73", fontSize: "0.85rem" }}>
          Invertido: <strong style={{ color: "#f5f5f7" }}>${tr.total_invertido.toLocaleString("es-CO", { maximumFractionDigits: 0 })}</strong>
          {" → "}Hoy: <strong style={{ color: "#f5f5f7" }}>${tr.total_valor.toLocaleString("es-CO", { maximumFractionDigits: 0 })}</strong>
          {" "}<span style={{ color: gc }}>({tr.rentabilidad_total > 0 ? "+" : ""}{tr.rentabilidad_total}%)</span>
        </div>
      </div>
      <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24, overflowX: "auto" }}>
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
      </div>
    </>
  );
}

// ── Historical section ───────────────────────────────────────

function HistoricoSection({ historico }: { historico: DashboardData["historico"] }) {
  if (!historico.length) return (
    <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24 }}>
      <p style={{ color: "#6e6e73", textAlign: "center" }}>Aún no hay registros históricos. El sistema guardará uno automáticamente cada día.</p>
    </div>
  );
  const ul  = historico[historico.length - 1];
  const pr  = historico[0];
  const gac = ul.resumen.ganancia_total;
  const rac = ul.resumen.rentabilidad_total;
  return (
    <>
      <SectionTitle>Resumen Acumulado</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 16 }}>
        {[
          { label: "Días registrados", value: historico.length, sub: `desde ${pr.fecha}` },
          { label: "Valor actual",     value: `$${ul.resumen.total_valor.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`, sub: "COP", color: "#30d158" },
          { label: "Ganancia acumulada", value: `${gac > 0 ? "+" : ""}$${gac.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`, sub: "COP real", color: gac > 0 ? "#30d158" : "#ff453a" },
          { label: "Rentabilidad total", value: `${rac > 0 ? "+" : ""}${rac}%`, sub: "desde inicio", color: rac > 0 ? "#30d158" : "#ff453a" },
        ].map(t => (
          <div key={t.label} style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24 }}>
            <h3 style={{ fontSize: "0.72rem", fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "#6e6e73", marginBottom: 12 }}>{t.label}</h3>
            <div style={{ fontSize: "2rem", fontWeight: 600, letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 4, color: (t as { color?: string }).color ?? "#f5f5f7" }}>{t.value}</div>
            <div style={{ fontSize: "0.8rem", color: "#6e6e73" }}>{t.sub}</div>
          </div>
        ))}
      </div>
      <SectionTitle>Registro Diario</SectionTitle>
      <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, padding: 24, overflowX: "auto" }}>
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
      </div>
    </>
  );
}
