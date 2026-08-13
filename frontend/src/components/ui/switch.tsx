"use client";

interface SwitchProps {
  on: boolean;
  onChange: (nuevo: boolean) => void;
  color?: string;
  disabled?: boolean;
  title?: string;
}

// Toggle compacto reutilizable -- no existía ningún componente Switch en el
// design system antes de esto (los "toggles" previos eran botones normales
// con estilo condicional). Usado para monitoreo de compra/venta, maestro y
// por activo.
export function Switch({ on, onChange, color = "#0071e3", disabled, title }: SwitchProps) {
  return (
    <button
      type="button"
      title={title}
      aria-pressed={on}
      disabled={disabled}
      onClick={(e) => { e.stopPropagation(); if (!disabled) onChange(!on); }}
      style={{
        width: 38, height: 22, borderRadius: 980, position: "relative",
        flexShrink: 0, border: "none", padding: 0,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        background: on ? color : "rgba(255,255,255,0.12)",
        transition: "background 0.2s ease",
      }}
    >
      <span
        style={{
          position: "absolute", top: 2, left: on ? 18 : 2,
          width: 18, height: 18, borderRadius: "50%",
          background: on ? "#fff" : "#c7ccd3",
          transition: "left 0.2s ease",
        }}
      />
    </button>
  );
}
