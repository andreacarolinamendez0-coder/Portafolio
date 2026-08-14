"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AvisoFlotante } from "@/components/ui/aviso-flotante";
import type { PrecioRT, RangoTicker, MonitoreoMap } from "@/lib/api";

interface Props {
  archivo: string;
  mercadoAbierto: boolean;
  precios: Record<string, PrecioRT>;
  rangos: Record<string, RangoTicker>;
  monitoreo: MonitoreoMap;
}

// Cuenta señales ENTRAR/VENDER activas que además tienen el toggle de
// monitoreo prendido para ese ticker+tipo (sin eso, la señal existe pero el
// usuario decidió no vigilarla, no tiene sentido molestarlo con ella). Usa
// `precios` con mercado abierto (dato en vivo) o `rangos` precalculado del
// día cuando está cerrado -- mismo criterio que ya usa monitor/page.tsx.
function contarSenales(
  mercadoAbierto: boolean,
  precios: Record<string, PrecioRT>,
  rangos: Record<string, RangoTicker>,
  monitoreo: MonitoreoMap
) {
  const fuente: Record<string, PrecioRT | RangoTicker> = mercadoAbierto ? precios : rangos;
  let compra = 0;
  let venta = 0;
  for (const [ticker, datos] of Object.entries(fuente || {})) {
    const mon = monitoreo[ticker];
    if (!mon || !datos) continue;
    if (mon.compra && datos.puede_entrar) compra++;
    if (mon.venta && datos.puede_vender) venta++;
  }
  return { compra, venta };
}

// Aviso ambient de Atom: avisa desde Dashboard (o donde se monte) que hay
// señales activas en Monitor, sin que el usuario tenga que entrar ahí a
// revisar. Lectura pura del mismo payload que ya expone /api/precios-rt --
// sin cambios de backend.
export function AvisoSenalesMonitor({ archivo, mercadoAbierto, precios, rangos, monitoreo }: Props) {
  const router = useRouter();
  const [cerrado, setCerrado] = useState(false);

  const { compra, venta } = contarSenales(mercadoAbierto, precios, rangos, monitoreo);
  const total = compra + venta;
  if (total === 0 || cerrado) return null;

  const partes: string[] = [];
  if (compra > 0) partes.push(`${compra} de compra`);
  if (venta > 0) partes.push(`${venta} de venta`);

  return (
    <AvisoFlotante
      acento="#0071e3"
      titulo="Monitor"
      mensaje={`Atom está vigilando tus activos: tienes ${total} señal${total === 1 ? "" : "es"} activa${total === 1 ? "" : "s"} (${partes.join(" y ")}).`}
      ctaLabel="Ir a Monitor"
      onCta={() => router.push(`/portafolio/${archivo}/monitor`)}
      onCerrar={() => setCerrado(true)}
    />
  );
}
