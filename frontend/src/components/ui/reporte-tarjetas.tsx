"use client";
import React from "react";
import { GlassPanel } from "@/components/ui/glass-panel";

const COLORES = ["#0071e3", "#30d158", "#ff9f0a", "#bf5af2", "#ff453a", "#5ac8fa", "#ffd60a", "#64d2ff", "#ff375f", "#a2845e"];

interface Escenario { pesimista: number; base: number; optimista: number }
interface Proyeccion {
  anios: number;
  total_aportado: number;
  sin_dca: Escenario;
  con_dca: Escenario | null;
  cdt_real: number;
  cdt_real_dca: number | null;
  ventaja_vs_cdt: number;
  ventaja_dca_vs_cdt: number | null;
}
export interface DatosReporte {
  perfil: string;
  horizonte: number;
  composicion: Record<string, number>;
  metricas: { retorno_anual: number; volatilidad: number; sharpe: number; max_drawdown: number };
  inflacion_col: number;
  cdt_ref: number;
  inversion_inicial: number;
  aporte_dca: number;
  frecuencia_meses: number;
  proyecciones: Proyeccion[];
}

const fmt = (n: number) => "$" + Math.round(n).toLocaleString("es-CO");
const fmtM = (n: number) => {
  if (Math.abs(n) >= 1_000_000) return "$" + (n / 1_000_000).toFixed(2) + "M";
  if (Math.abs(n) >= 1_000) return "$" + (n / 1_000).toFixed(0) + "K";
  return "$" + Math.round(n).toLocaleString("es-CO");
};

export function ReporteTarjetas({ datos, notaNuevos, advertenciaCategoria }: { datos: DatosReporte; notaNuevos?: string; advertenciaCategoria?: string }) {
  const hayDca = datos.aporte_dca > 0;
  const m = datos.metricas;
  const composArr = Object.entries(datos.composicion).sort((a, b) => b[1] - a[1]);

  return (
    <div style={{ marginTop: 16 }}>

      {/* Métricas */}
      <p style={s.seccion}>Métricas del portafolio</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginBottom: 18 }}>
        {[
          { label: "Retorno anual", value: `${m.retorno_anual.toFixed(2)}%`, color: "#30d158" },
          { label: "Volatilidad", value: `${m.volatilidad.toFixed(2)}%` },
          { label: "Sharpe ratio", value: m.sharpe.toFixed(2) },
          { label: "Max Drawdown", value: `${m.max_drawdown.toFixed(2)}%`, color: "#ff453a" },
        ].map(c => (
          <GlassPanel key={c.label} style={{ marginBottom: 0, padding: "14px 16px" }}>
            <p style={{ fontSize: 11, color: "var(--text-3)", margin: "0 0 6px", textTransform: "uppercase", letterSpacing: "0.05em" }}>{c.label}</p>
            <p style={{ fontSize: 22, fontWeight: 600, margin: 0, letterSpacing: "-0.02em", color: c.color ?? "var(--text)", fontVariantNumeric: "tabular-nums" }}>{c.value}</p>
          </GlassPanel>
        ))}
      </div>

      {/* Proyecciones por horizonte */}
      <p style={s.seccion}>Proyección — valor real (poder de compra)</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 14 }}>
        {datos.proyecciones.map((p, i) => {
          const color = COLORES[i % COLORES.length];
          const esc = hayDca && p.con_dca ? p.con_dca : p.sin_dca;
          const cdt = hayDca && p.cdt_real_dca !== null ? p.cdt_real_dca : p.cdt_real;
          const ventaja = hayDca && p.ventaja_dca_vs_cdt !== null ? p.ventaja_dca_vs_cdt : p.ventaja_vs_cdt;
          return (
            <GlassPanel key={p.anios} style={{ marginBottom: 0, padding: "16px 17px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: color }} />
                  <span style={{ fontSize: 13, color: "var(--text-2)" }}>En {p.anios} años</span>
                </div>
                {hayDca && <span style={{ fontSize: 10.5, color: "var(--text-3)", fontVariantNumeric: "tabular-nums" }}>aportado {fmtM(p.total_aportado)}</span>}
              </div>
              <p style={{ fontSize: 22, fontWeight: 600, margin: 0, letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}>{fmt(esc.base)}</p>
              <p style={{ fontSize: 11.5, color: "var(--text-3)", margin: "2px 0 10px" }}>base{hayDca ? " · con aportes DCA" : ""}</p>

              <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                <div style={{ flex: 1, background: "var(--bg-2)", borderRadius: 8, padding: "6px 8px" }}>
                  <p style={{ fontSize: 10, color: "var(--text-3)", margin: 0 }}>Pesimista</p>
                  <p style={{ fontSize: 13, margin: "1px 0 0", fontVariantNumeric: "tabular-nums" }}>{fmtM(esc.pesimista)}</p>
                </div>
                <div style={{ flex: 1, background: "var(--bg-2)", borderRadius: 8, padding: "6px 8px" }}>
                  <p style={{ fontSize: 10, color: "var(--text-3)", margin: 0 }}>Optimista</p>
                  <p style={{ fontSize: 13, margin: "1px 0 0", fontVariantNumeric: "tabular-nums" }}>{fmtM(esc.optimista)}</p>
                </div>
              </div>

              <div style={{ borderTop: "1px solid var(--glass-border)", paddingTop: 9, fontSize: 12, lineHeight: 1.5 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                  <span style={{ color: "var(--text-3)" }}>CDT daría</span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>{fmt(cdt)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-3)" }}>Ventaja</span>
                  <span style={{ color: ventaja >= 0 ? "#30d158" : "#ff453a", fontVariantNumeric: "tabular-nums" }}>{ventaja >= 0 ? "+" : ""}{fmt(ventaja)}</span>
                </div>
              </div>
            </GlassPanel>
          );
        })}
      </div>

      {/* Frase explicativa */}
      <div style={{ background: "rgba(0,113,227,0.08)", border: "1px solid rgba(0,113,227,0.18)", borderRadius: 12, padding: "12px 14px", marginBottom: 18 }}>
        <p style={{ fontSize: 12.5, color: "var(--text-2)", margin: 0, lineHeight: 1.6 }}>
          Si ese dinero lo dejaras en un certificado de depósito a término (CDT) durante este plazo, tendrías la cifra de “CDT daría”. El número grande es tu portafolio en valor real —descontando la inflación—, es decir, el verdadero poder de compra de tu dinero al final del periodo. “Pesimista” y “optimista” marcan el rango probable.
        </p>
      </div>

      {/* Composición */}
      <p style={s.seccion}>Composición</p>
      <GlassPanel style={{ marginBottom: (notaNuevos || advertenciaCategoria) ? 14 : 0 }}>
        {composArr.map(([ticker, peso], i) => {
          const color = COLORES[i % COLORES.length];
          return (
            <div key={ticker} style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 0", borderBottom: i < composArr.length - 1 ? "1px solid var(--glass-border)" : "none" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9, width: 88 }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: color, flexShrink: 0 }} />
                <span style={{ fontSize: 14, fontWeight: 600 }}>{ticker}</span>
              </div>
              <div style={{ flex: 1, background: "var(--bg-2)", borderRadius: 980, height: 7, overflow: "hidden" }}>
                <div style={{ background: color, height: "100%", width: `${(peso * 100).toFixed(1)}%`, borderRadius: 980 }} />
              </div>
              <span style={{ width: 52, textAlign: "right", fontSize: 14, fontWeight: 500, fontVariantNumeric: "tabular-nums" }}>{(peso * 100).toFixed(1)}%</span>
            </div>
          );
        })}
      </GlassPanel>

      {/* Advertencia de concentración por categoría */}
      {advertenciaCategoria && (
        <div style={{ background: "rgba(255,159,10,0.08)", border: "1px solid rgba(255,159,10,0.2)", borderRadius: 10, padding: "10px 13px", marginBottom: notaNuevos ? 10 : 0 }}>
          <p style={{ fontSize: 12, color: "#ff9f0a", margin: 0, lineHeight: 1.5 }}>{advertenciaCategoria}</p>
        </div>
      )}

      {/* Nota de activos nuevos */}
      {notaNuevos && (
        <div style={{ background: "rgba(255,159,10,0.08)", border: "1px solid rgba(255,159,10,0.2)", borderRadius: 10, padding: "10px 13px" }}>
          <p style={{ fontSize: 12, color: "#ff9f0a", margin: 0, lineHeight: 1.5 }}>{notaNuevos}</p>
        </div>
      )}

      {/* Pie: inflación / CDT ref */}
      <p style={{ fontSize: 11, color: "var(--text-3)", marginTop: 14, lineHeight: 1.5 }}>
        Valores en pesos de hoy, deflactados con inflación Colombia {datos.inflacion_col.toFixed(1)}% anual · CDT de referencia: {datos.cdt_ref.toFixed(2)}% anual
      </p>

    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  seccion: { fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", margin: "0 0 10px" },
};