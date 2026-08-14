"use client";
import { useState, Fragment } from "react";
import { GlassPanel } from "@/components/ui/glass-panel";
import type { MetricaActivo, MetricaPortafolio, PanelComparacion } from "@/lib/api";

interface Props {
  porActivo: MetricaActivo[];
  objetivo: PanelComparacion;
  actual: PanelComparacion;
}

const POSITIVO = "#34d17c";
const NEGATIVO = "#f2564a";
const AZUL = "#4f8dfd";
const AMBAR = "#e0ac2b";

function fmtPct(v: number | null | undefined, decimales = 1) {
  return v == null ? "—" : `${v.toFixed(decimales)}%`;
}

function Stat({ label, valor, color, acento }: { label: string; valor: string; color?: string; acento?: string }) {
  return (
    <div style={{ background: "var(--bg-2)", border: "1px solid var(--glass-border)", borderLeft: `2.5px solid ${acento ?? AZUL}`, borderRadius: 12, padding: "13px 14px" }}>
      <p style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-3)", margin: "0 0 6px" }}>{label}</p>
      <p style={{ fontSize: 18, fontWeight: 700, margin: 0, color: color ?? "var(--text)" }}>{valor}</p>
    </div>
  );
}

function GroupCard({ tinte, dotColor, titulo, sub, m, congelada }: {
  tinte: string; dotColor: string; titulo: string; sub: string;
  m: MetricaPortafolio | null; congelada?: MetricaPortafolio | null;
}) {
  return (
    <div style={{
      borderRadius: 20, padding: "20px 20px 18px", border: `1px solid ${tinte}55`,
      background: `radial-gradient(140% 100% at 0% 0%, ${tinte}26, transparent 60%), rgba(255,255,255,0.015)`,
      position: "relative",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: dotColor, boxShadow: `0 0 8px ${dotColor}99`, flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700, color: dotColor }}>{titulo}</div>
          <div style={{ fontSize: 10.5, color: "var(--text-3)" }}>{sub}</div>
        </div>
      </div>
      {m ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 9 }}>
            <Stat label="Retorno anual" valor={fmtPct(m.retorno_anual)} color={m.retorno_anual >= 0 ? POSITIVO : NEGATIVO} acento={dotColor} />
            <Stat label="Volatilidad" valor={fmtPct(m.volatilidad)} acento={dotColor} />
            <Stat label="Max drawdown" valor={fmtPct(m.max_drawdown)} color={NEGATIVO} acento={NEGATIVO} />
            {m.sharpe != null ? <Stat label="Sharpe" valor={m.sharpe.toFixed(2)} acento={dotColor} /> : <div />}
          </div>
          {congelada && (
            <p style={{ fontSize: 10.5, color: "var(--text-3)", margin: "12px 0 0" }}>
              Proyección original congelada el {congelada.fecha ?? "—"}: retorno {fmtPct(congelada.retorno_anual)}
            </p>
          )}
        </>
      ) : (
        <div style={{ minHeight: 150, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", gap: 8 }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, background: "rgba(79,141,253,0.14)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15 }}>⏳</div>
          <p style={{ fontSize: 12, color: "var(--text-2)", margin: 0, lineHeight: 1.5, maxWidth: 220 }}>
            Aún no hay suficiente historial real para calcular esto de forma confiable.
          </p>
        </div>
      )}
    </div>
  );
}

const th: React.CSSProperties = {
  textAlign: "right", fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.03em",
  color: "var(--text-3)", padding: "0 8px 10px", fontWeight: 600,
};
const celda: React.CSSProperties = {
  textAlign: "right", fontSize: "0.85rem", padding: "10px 8px",
  borderTop: "1px solid var(--glass-border)", fontVariantNumeric: "tabular-nums",
};

function EstadoPill({ estado }: { estado: MetricaActivo["estado"] }) {
  const enMeta = estado === "en_meta";
  return (
    <span style={{
      fontSize: 9.5, fontWeight: 700, padding: "2px 8px", borderRadius: 980, marginLeft: 8, letterSpacing: "0.02em",
      background: enMeta ? "rgba(79,141,253,0.13)" : "rgba(224,172,43,0.14)",
      color: enMeta ? AZUL : AMBAR,
    }}>
      {enMeta ? "EN META" : "FUERA DE META"}
    </span>
  );
}

function FilaComun({ f }: { f: MetricaActivo }) {
  return (
    <>
      <td style={celda}>{fmtPct(f.rentabilidad_real)}</td>
      <td style={celda}>{fmtPct(f.volatilidad_real)}</td>
      <td style={{ ...celda, color: NEGATIVO }}>{fmtPct(f.drawdown_real)}</td>
      <td style={celda}>
        {f.sortino_historico_motor != null ? (
          <span style={{ background: "rgba(79,141,253,0.13)", color: AZUL, fontWeight: 700, fontSize: 11.5, padding: "2px 9px", borderRadius: 980 }}>
            {f.sortino_historico_motor.toFixed(2)}
          </span>
        ) : "—"}
      </td>
      <td style={celda}>{fmtPct(f.volatilidad_historica_motor)}</td>
    </>
  );
}

const PANELES = [
  { id: "objetivo" as const, label: "Portafolio objetivo", sub: "Meta (proyección viva) vs. real — solo posiciones vigentes" },
  { id: "real" as const, label: "Portafolio real", sub: "Proyección viva vs. real — incluye activos fuera de meta" },
];

export function TablaFinancieraActivos({ porActivo, objetivo, actual }: Props) {
  const [panel, setPanel] = useState<"objetivo" | "real">("objetivo");
  if (!porActivo.length) return null;

  const filasObjetivo = porActivo.filter(f => f.estado === "en_meta");

  return (
    <GlassPanel>
      <p style={{ color: "var(--text)", fontSize: 14, fontWeight: 600, margin: "0 0 4px" }}>
        Rendimiento: proyectado vs real
      </p>
      <p style={{ color: "var(--text-3)", fontSize: 12, margin: "0 0 20px" }}>
        A nivel de portafolio completo, y por activo abajo.
      </p>

      {/* Selector "dot tabs" */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 22, flexWrap: "wrap" }}>
        {PANELES.map((p, i) => (
          <Fragment key={p.id}>
            <div
              onClick={() => setPanel(p.id)}
              style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", padding: "6px 8px 6px 0", opacity: panel === p.id ? 1 : 0.45, transition: "opacity .2s" }}
            >
              <span style={{
                width: 9, height: 9, borderRadius: "50%", flexShrink: 0, transition: "all .2s",
                border: `1.5px solid ${panel === p.id ? AZUL : "var(--text-3)"}`,
                background: panel === p.id ? AZUL : "transparent",
                boxShadow: panel === p.id ? `0 0 9px ${AZUL}8c` : "none",
              }} />
              <div>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--text)" }}>{p.label}</div>
                <div style={{ fontSize: 10.5, color: "var(--text-3)", marginTop: 1 }}>{p.sub}</div>
              </div>
            </div>
            {i < PANELES.length - 1 && <span style={{ flex: "0 0 46px", height: 1, background: "var(--glass-border)", margin: "0 4px" }} />}
          </Fragment>
        ))}
      </div>

      {panel === "objetivo" ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
            <GroupCard tinte={AMBAR} dotColor={AMBAR} titulo="Meta · Proyección viva" sub="Recalculada hoy con datos actuales"
              m={objetivo.proyeccion_viva} congelada={objetivo.proyeccion_congelada} />
            <GroupCard tinte={AZUL} dotColor={AZUL} titulo="Real" sub="Con lo que realmente tienes hoy" m={objetivo.real} />
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...th, textAlign: "left" }}>Activo</th>
                  <th style={th}>Meta</th>
                  <th style={th}>Real</th>
                  <th style={th}>Rent. real</th>
                  <th style={th}>Vol. real</th>
                  <th style={th}>Drawdown real</th>
                  <th style={th}>Sortino histórico</th>
                  <th style={th}>Vol. histórica (motor)</th>
                </tr>
              </thead>
              <tbody>
                {filasObjetivo.map(f => {
                  const metaPct = (f.peso_meta ?? 0) * 100;
                  const realPct = (f.peso_real ?? 0) * 100;
                  return (
                    <tr key={f.activo}>
                      <td style={{ fontSize: "0.85rem", fontWeight: 700, padding: "10px 8px", borderTop: "1px solid var(--glass-border)" }}>{f.activo}</td>
                      <td style={celda}>{f.peso_meta != null ? fmtPct(metaPct) : "—"}</td>
                      <td style={celda}>{f.peso_real != null ? fmtPct(realPct) : "—"}</td>
                      <FilaComun f={f} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p style={{ fontSize: 10.5, color: "var(--text-3)", lineHeight: 1.6, margin: "16px 0 0", paddingTop: 14, borderTop: "1px solid var(--glass-border)" }}>
            Esta vista compara solo los activos que hoy forman parte de tu composición objetivo. Los activos que
            salieron de la meta pero aún sostienes no aparecen aquí — revisa &quot;Portafolio real&quot; para verlos.
          </p>
        </>
      ) : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
            <GroupCard tinte={AZUL} dotColor={AZUL} titulo="Proyección viva" sub="Recalculada con tus posiciones reales, incl. fuera de meta"
              m={actual.proyeccion_viva} />
            <GroupCard tinte={AZUL} dotColor={AZUL} titulo="Real" sub="Con lo que realmente tienes hoy, todo incluido" m={actual.real} />
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...th, textAlign: "left" }}>Activo</th>
                  <th style={th}>Peso real</th>
                  <th style={th}>Rent. real</th>
                  <th style={th}>Vol. real</th>
                  <th style={th}>Drawdown real</th>
                  <th style={th}>Sortino histórico</th>
                  <th style={th}>Vol. histórica (motor)</th>
                </tr>
              </thead>
              <tbody>
                {porActivo.map(f => {
                  const realPct = (f.peso_real ?? 0) * 100;
                  return (
                    <tr key={f.activo}>
                      <td style={{ fontSize: "0.85rem", fontWeight: 700, padding: "10px 8px", borderTop: "1px solid var(--glass-border)" }}>
                        {f.activo}<EstadoPill estado={f.estado} />
                      </td>
                      <td style={celda}>{f.peso_real != null ? fmtPct(realPct) : "—"}</td>
                      <FilaComun f={f} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p style={{ fontSize: 10.5, color: "var(--text-3)", lineHeight: 1.6, margin: "16px 0 0", paddingTop: 14, borderTop: "1px solid var(--glass-border)" }}>
            Esta vista incluye todos los activos que sostienes hoy, incluyendo los que salieron de la composición
            objetivo. La proyección viva usa tus pesos reales, no los pesos de la meta — por eso puede diferir del
            panel &quot;Portafolio objetivo&quot;.
          </p>
        </>
      )}

      <p style={{ fontSize: 11, color: "var(--text-3)", margin: "14px 0 0" }}>
        &quot;Vol. histórica (motor)&quot; y &quot;Sortino histórico&quot; son lo que el motor vio de cada activo al
        construir tu portafolio — no una predicción de rentabilidad futura por activo individual (eso el
        motor deliberadamente no lo estima).
      </p>
    </GlassPanel>
  );
}
