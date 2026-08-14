"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AvisoFlotante } from "@/components/ui/aviso-flotante";
import type { DesviacionComposicion } from "@/lib/api";

interface Props {
  archivo: string;
  desviacion: DesviacionComposicion | null | undefined;
}

// Aviso de Atom cuando Seguimiento tiene algo que decir sobre la composicion
// real vs la meta. Silencio total mientras el portafolio todavia se esta
// construyendo (desviacion.aplica false) -- ver
// dashboard.py:calcular_desviacion_composicion. Se renderiza dentro de un
// <AvisosHost> (aviso-flotante.tsx) en cada página que lo use.
export function AvisoSeguimiento({ archivo, desviacion }: Props) {
  const router = useRouter();
  const [cerrado, setCerrado] = useState(false);

  if (!desviacion?.aplica || cerrado) return null;

  const desviado = desviacion.necesita_rebalanceo;

  return (
    <AvisoFlotante
      acento={desviado ? "#ff9f0a" : "#30d158"}
      titulo="Seguimiento"
      mensaje={
        desviado
          ? "Hoy Seguimiento miró tu portafolio: hay ajustes por hacer, tu composición se desvió de la meta."
          : "Hoy Seguimiento miró tu portafolio: seguimos encaminados a tus metas."
      }
      detalle={
        desviado && desviacion.desviacion_total_pp != null
          ? `Desviación total: ${desviacion.desviacion_total_pp.toFixed(1)} puntos porcentuales.`
          : undefined
      }
      ctaLabel={desviado ? "Ir al Analista" : undefined}
      onCta={desviado ? () => router.push(`/portafolio/${archivo}/analista?motivo=rebalanceo`) : undefined}
      onCerrar={() => setCerrado(true)}
    />
  );
}
