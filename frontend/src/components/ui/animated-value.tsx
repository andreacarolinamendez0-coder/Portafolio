"use client";
import { useEffect, useRef, useState } from "react";
import CountUp from "react-countup";

interface AnimatedValueProps {
  /** Número ya calculado, listo para mostrar (ej. total_valor en COP). */
  value: number;
  /** Formatea el número final para mostrarlo (reusa mostrarMonto / toFixed, etc). */
  format: (n: number) => string;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Número tipo "ticker" de pantalla de trading: cuenta hacia el nuevo valor
 * (400-600ms) y dispara un flash de fondo verde/rojo según suba o baje.
 * No toca el color del texto — eso lo maneja el padre según el signo.
 */
export function AnimatedValue({ value, format, className, style }: AnimatedValueProps) {
  // Valor inicial fijo: primer render no debe "contar" desde 0, solo se
  // anima cuando `value` cambia en renders posteriores (preserveValue).
  const valorInicialRef = useRef(value);
  const anteriorRef     = useRef(value); // "usePrevious" — se lee antes de actualizar
  const [flash, setFlash] = useState<"up" | "down" | null>(null);

  // react-countup reinicia la animación (reset + restart desde `start`) cada
  // vez que `formattingFn` cambia de referencia (ver su efecto interno que
  // depende de props.formattingFn). Si el caller pasa `format` como arrow
  // inline (ej. monitor/page.tsx), es una función nueva en cada render — y
  // como este componente vive dentro de un árbol que re-renderiza cada
  // ~100ms (anillo de "próximo refresh"), el reinicio nunca deja completar
  // la animación y el número queda pegado cerca del valor con el que montó
  // (bug: header de DetallePanel mostrando el precio del ticker anterior).
  // Envolvemos `format` en una referencia estable para que `formattingFn`
  // nunca cambie de identidad, sin dejar de usar la versión más reciente.
  const formatRef = useRef(format);
  formatRef.current = format;
  const formatEstable = useRef((n: number) => formatRef.current(n)).current;

  useEffect(() => {
    const anterior = anteriorRef.current;
    if (value > anterior) setFlash("up");
    else if (value < anterior) setFlash("down");
    anteriorRef.current = value;

    if (value !== anterior) {
      const t = setTimeout(() => setFlash(null), 420);
      return () => clearTimeout(t);
    }
  }, [value]);

  const flashBg = flash === "up"
    ? "rgba(48,209,88,0.15)"
    : flash === "down"
      ? "rgba(255,69,58,0.15)"
      : "transparent";

  return (
    <span className={className} style={{ position: "relative", display: "inline-block", ...style }}>
      <span
        aria-hidden
        style={{
          position: "absolute",
          inset: "-4px -10px",
          borderRadius: 8,
          background: flashBg,
          opacity: flash ? 1 : 0,
          filter: "blur(3px)",
          transition: flash ? "opacity 160ms ease-out" : "opacity 340ms ease-in",
          pointerEvents: "none",
        }}
      />
      <span style={{ position: "relative" }}>
        <CountUp
          start={valorInicialRef.current}
          end={value}
          duration={0.5}
          preserveValue
          useEasing
          formattingFn={formatEstable}
        />
      </span>
    </span>
  );
}
