"use client";
import { GlassPanel } from "@/components/ui/glass-panel";
import type { MetricaActivo, MetricaPortafolio } from "@/lib/api";

interface Props {
  porActivo: MetricaActivo[];
  proyectado: MetricaPortafolio | null;
  real: MetricaPortafolio | null;
}

// Verde/rojo: la convencion YA establecida en el resto de la app para
// ganancia/perdida (reporte-tarjetas.tsx, PosicionesSection) -- se reutiliza
// aqui para sub/sobreponderado por consistencia de significado dentro de la
// misma app, no por ser la pareja mas "optima" en aislado.
const POSITIVO = "#30d158";
const NEGATIVO = "#ff453a";
const UMBRAL_RESALTAR_PP = 5; // mismo umbral que UMBRAL_DESVIACION_ACTIVO en dashboard.py

function fmtPct(v: number | null | undefined, decimales = 1) {
  return v == null ? "—" : `${v.toFixed(decimales)}%`;
}

function colorDelta(pp: number) {
  if (Math.abs(pp) < UMBRAL_RESALTAR_PP) return "var(--text-2)";
  return pp > 0 ? NEGATIVO : POSITIVO; // sobreponderado = rojo, subponderado = verde (ambos "hay que ajustar")
}

function TarjetaMetrica({ label, valor, color }: { label: string; valor: string; color?: string }) {
  return (
    <GlassPanel style={{ padding: "12px 14px", marginBottom: 0 }}>
      <p style={{ fontSize: 10.5, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 4px" }}>
        {label}
      </p>
      <p style={{ fontSize: 19, fontWeight: 600, letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums", margin: 0, color: color ?? "var(--text)" }}>
        {valor}
      </p>
    </GlassPanel>
  );
}

function BloqueMetricas({ titulo, m, nota }: { titulo: string; m: MetricaPortafolio | null; nota?: string }) {
  return (
    <div>
      <p style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", margin: "0 0 8px" }}>
        {titulo}{nota ? ` — ${nota}` : ""}
      </p>
      {m ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8 }}>
          <TarjetaMetrica label="Retorno anual" valor={fmtPct(m.retorno_anual)} color={m.retorno_anual >= 0 ? POSITIVO : NEGATIVO} />
          <TarjetaMetrica label="Volatilidad" valor={fmtPct(m.volatilidad)} />
          <TarjetaMetrica label="Max drawdown" valor={fmtPct(m.max_drawdown)} color={NEGATIVO} />
          {m.sharpe != null && <TarjetaMetrica label="Sharpe" valor={m.sharpe.toFixed(2)} />}
        </div>
      ) : (
        <p style={{ fontSize: 12.5, color: "var(--text-3)", margin: 0 }}>
          Aún no hay suficiente historial real para calcular esto de forma confiable.
        </p>
      )}
    </div>
  );
}

export function TablaFinancieraActivos({ porActivo, proyectado, real }: Props) {
  if (!porActivo.length) return null;

  const fuenteTxt =
    proyectado?.fuente === "guardado_al_aplicar"
      ? `guardado el ${proyectado.fecha ?? ""}`
      : proyectado?.fuente === "recalculado_hoy"
      ? "recalculado hoy con datos actuales"
      : undefined;

  return (
    <GlassPanel>
      <p style={{ color: "var(--text)", fontSize: 14, fontWeight: 600, margin: "0 0 4px" }}>
        Rendimiento: proyectado vs real
      </p>
      <p style={{ color: "var(--text-3)", fontSize: 12, margin: "0 0 16px" }}>
        A nivel de portafolio completo, y por activo abajo.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
        <BloqueMetricas titulo="Proyectado" m={proyectado} nota={fuenteTxt} />
        <BloqueMetricas titulo="Real" m={real} />
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr>
              {["Activo", "Meta", "Real", "Rent. real", "Vol. real", "Drawdown real", "Sortino histórico", "Vol. histórica (motor)"].map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: h === "Activo" ? "left" : "right",
                    fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.03em",
                    color: "var(--text-3)", padding: "6px 8px",
                    borderBottom: "1px solid var(--glass-border)",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {porActivo.map((f) => {
              const pesoMetaPct = (f.peso_meta ?? 0) * 100;
              const pesoRealPct = (f.peso_real ?? 0) * 100;
              const deltaPp = pesoRealPct - pesoMetaPct;
              return (
                <tr key={f.activo}>
                  <td style={{ fontSize: "0.85rem", fontWeight: 600, padding: "8px", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    {f.activo}
                  </td>
                  <td style={celda}>{f.peso_meta != null ? fmtPct(pesoMetaPct) : "—"}</td>
                  <td style={{ ...celda, color: colorDelta(deltaPp), fontWeight: Math.abs(deltaPp) >= UMBRAL_RESALTAR_PP ? 600 : 400 }}>
                    {f.peso_real != null ? fmtPct(pesoRealPct) : "—"}
                  </td>
                  <td style={{ ...celda, color: (f.rentabilidad_real ?? 0) >= 0 ? POSITIVO : NEGATIVO }}>
                    {fmtPct(f.rentabilidad_real)}
                  </td>
                  <td style={celda}>{fmtPct(f.volatilidad_real)}</td>
                  <td style={{ ...celda, color: NEGATIVO }}>{fmtPct(f.drawdown_real)}</td>
                  <td style={celda}>{f.sortino_historico_motor != null ? f.sortino_historico_motor.toFixed(2) : "—"}</td>
                  <td style={celda}>{fmtPct(f.volatilidad_historica_motor)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 11, color: "var(--text-3)", margin: "10px 0 0" }}>
        &quot;Vol. histórica (motor)&quot; y &quot;Sortino histórico&quot; son lo que el motor vio de cada activo al
        construir tu portafolio — no una predicción de rentabilidad futura por activo individual (eso el
        motor deliberadamente no lo estima).
      </p>
    </GlassPanel>
  );
}

const celda: React.CSSProperties = {
  textAlign: "right", fontSize: "0.85rem", padding: "8px",
  borderBottom: "1px solid rgba(255,255,255,0.04)",
};
