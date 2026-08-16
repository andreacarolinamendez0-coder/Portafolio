"use client";
import { GlassPanel } from "@/components/ui/glass-panel";
import type { MetricaActivo } from "@/lib/api";

interface Props {
  composicionMeta: Record<string, number>;
  composicionReal: Record<string, number>;
  porActivo?: MetricaActivo[];
}

function fmtUsd(v: number) {
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Widget "idea de corrección" (spec de rebalanceo 2026-08-14): por cada
// activo con peso meta, una sugerencia concreta en USD de hoy que reduciría
// la desviación -- SIEMPRE informativo, nunca fuerza ni redirige.
// Umbral único (2026-08-14): cualquier desviación no-cero (misma vara que
// el pill de "+X pp" de la leyenda, no la banda 5/25) dispara el mensaje.
// La banda de tolerancia (`banda_pp`/`dentro_de_banda`) ya NO decide el tono
// aquí -- por si sola no dice nada sobre si el portafolio se aleja de lo
// esperado; eso solo lo determina si la desviación real de volatilidad/
// drawdown dispara la Capa 2 (evaluar_disparo_rebalanceo), que es
// completamente independiente del peso.
function SugerenciaCorreccion({ fila }: { fila: MetricaActivo }) {
  if (fila.peso_meta == null) return null; // fuera de meta, no hay con que comparar

  if (!fila.accion_sugerida || fila.monto_sugerido_usd == null) {
    return (
      <p style={{ fontSize: 11, color: "var(--text-3)", margin: "4px 0 0" }}>
        Ya estás exactamente en tu peso objetivo.
      </p>
    );
  }

  const verbo = fila.accion_sugerida === "comprar" ? "comprar" : "vender";
  const texto = `Para acercar ${fila.activo} a su peso objetivo, podrías ${verbo} ${fmtUsd(fila.monto_sugerido_usd)} hoy` +
    (fila.fracciones_sugeridas != null ? ` (~${fila.fracciones_sugeridas} fracciones a precio actual).` : ".");

  return (
    <p style={{ fontSize: 11, margin: "4px 0 0", lineHeight: 1.5, color: "var(--text-2)" }}>
      {texto}
    </p>
  );
}

// Paleta categórica fija (orden estable por ticker, nunca ciclada dentro de
// un mismo portafolio salvo que haya más de 8 activos) -- mismo espíritu que
// la paleta validada (dataviz skill) que ya se usaba en el bar chart que
// esto reemplaza, extendida a más tonos porque un donut necesita un color
// por activo, no solo 2 (meta/real).
const PALETA = ["#4f8dfd", "#2fd4c0", "#a78bfa", "#fb923c", "#e0ac2b", "#34d17c", "#f2564a", "#60a5fa"];
const R = 58;
const CIRCUNFERENCIA = 2 * Math.PI * R;

function Donut({ segmentos, centroN, centroL }: {
  segmentos: { color: string; pct: number }[];
  centroN: number;
  centroL: string;
}) {
  let acumulado = 0;
  return (
    <div style={{ position: "relative", width: 150, height: 150 }}>
      <svg width="150" height="150" viewBox="0 0 150 150" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="75" cy="75" r={R} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="16" />
        {segmentos.filter(s => s.pct > 0.05).map((s, i) => {
          const largo = (s.pct / 100) * CIRCUNFERENCIA;
          const offset = -acumulado;
          acumulado += largo;
          return (
            <circle
              key={i} cx="75" cy="75" r={R} fill="none" stroke={s.color} strokeWidth="16"
              strokeDasharray={`${largo} ${CIRCUNFERENCIA - largo}`}
              strokeDashoffset={offset} strokeLinecap="round"
            />
          );
        })}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text)" }}>{centroN}</div>
        <div style={{ fontSize: 9.5, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{centroL}</div>
      </div>
    </div>
  );
}

export function ComposicionComparada({ composicionMeta, composicionReal, porActivo }: Props) {
  const filaPorActivo = new Map((porActivo ?? []).map(f => [f.activo, f]));
  const tickers = Array.from(new Set([...Object.keys(composicionMeta), ...Object.keys(composicionReal)]))
    .sort((a, b) => ((composicionMeta[b] ?? 0) + (composicionReal[b] ?? 0)) - ((composicionMeta[a] ?? 0) + (composicionReal[a] ?? 0)));

  if (!tickers.length) return null;

  const color = (t: string) => PALETA[tickers.indexOf(t) % PALETA.length];
  const metaSegs = tickers.map(t => ({ color: color(t), pct: (composicionMeta[t] ?? 0) * 100 }));
  const realSegs = tickers.map(t => ({ color: color(t), pct: (composicionReal[t] ?? 0) * 100 }));
  const nMeta = tickers.filter(t => (composicionMeta[t] ?? 0) > 0).length;
  const nReal = tickers.filter(t => (composicionReal[t] ?? 0) > 0).length;

  return (
    <GlassPanel>
      <p style={{ color: "var(--text)", fontSize: 20, fontWeight: 600, margin: "0 0 4px" }}>
        COMPOSICIÓN DE PORTAFOLIO: META VS REAL
      </p>
      <p style={{ color: "var(--text-3)", fontSize: 12, margin: "0 0 20px" }}>
        Qué te propusiste vs qué tienes hoy realmente, por activo.
      </p>

      <div style={{ display: "flex", gap: 28, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ textAlign: "center", flexShrink: 0 }}>
          <Donut segmentos={metaSegs} centroN={nMeta} centroL="activos" />
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", marginTop: 10, letterSpacing: "0.02em" }}>META</div>
        </div>
        <div style={{ textAlign: "center", flexShrink: 0 }}>
          <Donut segmentos={realSegs} centroN={nReal} centroL="con posición" />
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", marginTop: 10, letterSpacing: "0.02em" }}>REAL</div>
        </div>

        <div style={{ flex: 1, minWidth: 220, display: "flex", flexDirection: "column", gap: 10 }}>
          {tickers.map(t => {
            const metaPct = (composicionMeta[t] ?? 0) * 100;
            const realPct = (composicionReal[t] ?? 0) * 100;
            const delta = realPct - metaPct;
            // Direccion de la desviacion, no ganancia/perdida -- a proposito
            // NO reusa el verde/rojo de ganancia ya establecido en el resto
            // de la app (ver mockup de Andrea): sobreponderarse (subir) es
            // ambar, quedar por debajo de la meta (bajar) es verde.
            const subiendo = delta > 0.05;
            const bajando = delta < -0.05;
            const fila = filaPorActivo.get(t);
            return (
              <div key={t} style={{ padding: "9px 12px", borderRadius: 10, background: "var(--bg-2)", border: "1px solid var(--glass-border)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ width: 9, height: 9, borderRadius: 3, background: color(t), flexShrink: 0 }} />
                  <span style={{ fontSize: 12.5, fontWeight: 700, width: 50, flexShrink: 0 }}>{t}</span>
                  <span style={{ flex: 1, fontSize: 12, color: "var(--text-3)" }}>
                    Meta <b style={{ color: "var(--text)" }}>{metaPct.toFixed(1)}%</b>
                    <span style={{ margin: "0 6px" }}>→</span>
                    Real <b style={{ color: "var(--text)" }}>{realPct.toFixed(1)}%</b>
                  </span>
                  {(subiendo || bajando) && (
                    <span style={{
                      fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 980, marginLeft: "auto",
                      background: subiendo ? "rgba(251,146,60,0.14)" : "rgba(52,209,124,0.14)",
                      color: subiendo ? "#fb923c" : "#34d17c",
                    }}>
                      {delta > 0 ? "+" : ""}{delta.toFixed(1)}pp
                    </span>
                  )}
                </div>
                {fila && <SugerenciaCorreccion fila={fila} />}
              </div>
            );
          })}
        </div>
      </div>
    </GlassPanel>
  );
}
