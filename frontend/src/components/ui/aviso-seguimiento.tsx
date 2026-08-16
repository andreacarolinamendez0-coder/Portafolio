"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AvisoFlotante } from "@/components/ui/aviso-flotante";
import type { DesviacionComposicion, DisparoRebalanceo } from "@/lib/api";

interface Props {
  archivo: string;
  desviacion: DesviacionComposicion | null | undefined;
  disparo?: DisparoRebalanceo | null;
}

// Aviso de Atom sobre el estado de Seguimiento. Silencio total mientras el
// portafolio todavia se esta construyendo (desviacion.aplica false) -- ver
// dashboard.py:calcular_desviacion_composicion. Se renderiza dentro de un
// <AvisosHost> (aviso-flotante.tsx) en cada página que lo use.
//
// Spec de rebalanceo 2026-08-14: desviacion de PESOS (desviacion) y
// disparo de rebalanceo por METRICAS (disparo) son señales independientes.
// Solo `disparo.disparar` lleva al Analista -- pesos desviados por si solos
// nunca lo hacen, aunque SI se avisan (tono informativo, sin CTA).
export function AvisoSeguimiento({ archivo, desviacion, disparo }: Props) {
  const router = useRouter();
  const [cerrado, setCerrado] = useState(false);

  if (!desviacion?.aplica || cerrado) return null;

  const disparar = disparo?.disparar ?? false;
  const pesosDesviados = Boolean(desviacion.activos_desviados && Object.keys(desviacion.activos_desviados).length);

  const acento = disparar ? "#ff9f0a" : pesosDesviados ? "#4f8dfd" : "#30d158";

  let mensaje: string;
  let detalle: string | undefined;
  if (disparar) {
    const motivoTxt = disparo?.motivo === "drawdown" ? "el drawdown" : "la volatilidad";
    mensaje = `Seguimiento notó que ${motivoTxt} real de tu portafolio lleva ${disparo?.dias_fuera_de_rango} días seguidos fuera de lo que se esperaba.`;
    detalle = "Esto sí amerita revisar tu portafolio con el Analista.";
  } else if (pesosDesviados) {
    mensaje = "Hoy Seguimiento miró tu portafolio: algunos pesos se corrieron de la meta, pero tu rendimiento real sigue dentro de lo esperado.";
    detalle = "Estás dentro del rango — no es necesario actuar si no quieres. Revisa Composición para ver sugerencias puntuales por activo.";
  } else {
    mensaje = "Hoy Seguimiento miró tu portafolio: seguimos encaminados a tus metas.";
    detalle = undefined;
  }

  return (
    <AvisoFlotante
      acento={acento}
      titulo="Seguimiento"
      mensaje={mensaje}
      detalle={detalle}
      ctaLabel={disparar ? "Ir al Analista" : undefined}
      onCta={disparar ? () => router.push(`/portafolio/${archivo}/analista?motivo=rebalanceo`) : undefined}
      onCerrar={() => setCerrado(true)}
    />
  );
}
