"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AvisoFlotante } from "@/components/ui/aviso-flotante";

interface Props {
  archivo: string;
  trmCambio: number | null | undefined;
}

// Movimiento del dólar suficientemente fuerte como para que valga la pena
// que Atom lo note -- umbral fijo, sin IA (el modelo solo entra si el
// usuario abre la conversación desde el CTA). `trmCambio` ya viene calculado
// en macro.trm_cambio (ver dashboard.py:cargar_macro), no requiere cambios
// de backend.
const UMBRAL_PP = 1.5;

export function AvisoTrm({ archivo, trmCambio }: Props) {
  const router = useRouter();
  const [cerrado, setCerrado] = useState(false);

  if (trmCambio == null || Math.abs(trmCambio) < UMBRAL_PP || cerrado) return null;

  const subio = trmCambio > 0;

  return (
    <AvisoFlotante
      acento={subio ? "#ff9f0a" : "#30d158"}
      titulo="TRM"
      mensaje={`El dólar ${subio ? "subió" : "bajó"} ${Math.abs(trmCambio).toFixed(1)}% en el último mes — un movimiento fuera de lo normal.`}
      ctaLabel="Preguntarle a Atom"
      onCta={() => router.push(`/portafolio/${archivo}/bot`)}
      onCerrar={() => setCerrado(true)}
    />
  );
}
