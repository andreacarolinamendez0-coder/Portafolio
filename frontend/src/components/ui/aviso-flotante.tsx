"use client";
import type { ReactNode } from "react";
import { GlassPanel } from "@/components/ui/glass-panel";
import { LiquidButton } from "@/components/ui/liquid-glass-button";

// Contenedor de posicionamiento/stacking para los avisos flotantes de Atom.
// Vive en la misma esquina que la burbuja del asistente (asistente-flotante.tsx,
// bottom:20 right:20 zIndex:60) pero apilado arriba de ella (bottom:90,
// zIndex:50) para que nunca se pisen. column-reverse: el primer hijo en el
// JSX queda más cerca de la burbuja (mayor prioridad visual).
export function AvisosHost({ children }: { children: ReactNode }) {
  return (
    <div style={{
      position: "fixed", bottom: 90, right: 20, zIndex: 50, maxWidth: 340,
      display: "flex", flexDirection: "column-reverse", alignItems: "flex-end", gap: 12,
      pointerEvents: "none",
    }}>
      {children}
    </div>
  );
}

interface AvisoFlotanteProps {
  acento: string;
  titulo: string;
  mensaje: string;
  detalle?: string;
  ctaLabel?: string;
  onCta?: () => void;
  onCerrar: () => void;
}

// Panel individual -- misma apariencia que el AvisoSeguimiento original
// (GlassPanel con acento de color, header con punto+label, botón cerrar),
// ahora reusable para cualquier "Atom notó algo" (Seguimiento, Monitor, TRM).
export function AvisoFlotante({ acento, titulo, mensaje, detalle, ctaLabel, onCta, onCerrar }: AvisoFlotanteProps) {
  return (
    <GlassPanel
      style={{
        padding: 18, marginBottom: 0, pointerEvents: "auto",
        border: `1px solid ${acento}59`,
        boxShadow: `0 8px 30px rgba(0,0,0,0.35), 0 0 24px ${acento}1f`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: acento, flexShrink: 0 }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            {titulo}
          </span>
        </div>
        <button
          onClick={onCerrar}
          aria-label="Cerrar aviso"
          style={{ background: "none", border: "none", color: "var(--text-3)", cursor: "pointer", fontSize: 14, lineHeight: 1, padding: 2 }}
        >
          ✕
        </button>
      </div>

      <p style={{ fontSize: 13.5, lineHeight: 1.5, color: "var(--text)", margin: "10px 0 0" }}>{mensaje}</p>

      {detalle && (
        <p style={{ fontSize: 12, color: "var(--text-3)", margin: "6px 0 0" }}>{detalle}</p>
      )}

      {ctaLabel && onCta && (
        <div style={{ marginTop: 12 }}>
          <LiquidButton onClick={onCta} className="text-white font-semibold !px-5 !py-2 !text-sm">
            {ctaLabel}
          </LiquidButton>
        </div>
      )}
    </GlassPanel>
  );
}
