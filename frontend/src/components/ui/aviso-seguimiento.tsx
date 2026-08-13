"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { GlassPanel } from "@/components/ui/glass-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import type { DesviacionComposicion } from "@/lib/api";

interface Props {
  archivo: string;
  desviacion: DesviacionComposicion | null | undefined;
}

// Panel flotante que aparece una vez por carga de pagina cuando Seguimiento
// tiene algo que decir sobre la composicion real vs la meta. Silencio total
// mientras el portafolio todavia se esta construyendo (desviacion.aplica
// false) -- ver dashboard.py:calcular_desviacion_composicion.
export function AvisoSeguimiento({ archivo, desviacion }: Props) {
  const router = useRouter();
  const [cerrado, setCerrado] = useState(false);

  if (!desviacion?.aplica || cerrado) return null;

  const desviado = desviacion.necesita_rebalanceo;
  const colorAcento = desviado ? "#ff9f0a" : "#30d158";

  return (
    <div style={{ position: "fixed", bottom: 20, right: 20, zIndex: 50, maxWidth: 340 }}>
      <GlassPanel
        style={{
          padding: 18,
          marginBottom: 0,
          border: `1px solid ${desviado ? "rgba(255,159,10,0.35)" : "rgba(48,209,88,0.3)"}`,
          boxShadow: `0 8px 30px rgba(0,0,0,0.35), 0 0 24px ${desviado ? "rgba(255,159,10,0.12)" : "rgba(48,209,88,0.1)"}`,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: colorAcento, flexShrink: 0 }} />
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Seguimiento
            </span>
          </div>
          <button
            onClick={() => setCerrado(true)}
            aria-label="Cerrar aviso"
            style={{ background: "none", border: "none", color: "var(--text-3)", cursor: "pointer", fontSize: 14, lineHeight: 1, padding: 2 }}
          >
            ✕
          </button>
        </div>

        <p style={{ fontSize: 13.5, lineHeight: 1.5, color: "var(--text)", margin: "10px 0 0" }}>
          {desviado
            ? "Hoy Seguimiento miró tu portafolio: hay ajustes por hacer, tu composición se desvió de la meta."
            : "Hoy Seguimiento miró tu portafolio: seguimos encaminados a tus metas."}
        </p>

        {desviado && desviacion.desviacion_total_pp != null && (
          <p style={{ fontSize: 12, color: "var(--text-3)", margin: "6px 0 0" }}>
            Desviación total: {desviacion.desviacion_total_pp.toFixed(1)} puntos porcentuales.
          </p>
        )}

        {desviado && (
          <div style={{ marginTop: 12 }}>
            <LiquidButton
              onClick={() => router.push(`/portafolio/${archivo}/analista?motivo=rebalanceo`)}
              className="text-white font-semibold !px-5 !py-2 !text-sm"
            >
              Ir al Analista
            </LiquidButton>
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
