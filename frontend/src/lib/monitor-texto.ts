import type { PrecioRT, RangoTicker } from "@/lib/api";

// Texto templado (sin llamadas a Claude) para justificar una señal técnica.
// Se generó así porque el refresh de precios corre cada 4-9s — una llamada
// en vivo a un LLM por card sería muy cara y lenta a esa cadencia. Ver
// monitor/page.tsx para el consumo de estas funciones.

function zonaRSI(rsi: number): string {
  if (rsi < 30) return "sobreventa";
  if (rsi > 70) return "sobrecompra";
  return "zona neutral";
}

function esPrecioRT(p: PrecioRT | RangoTicker): p is PrecioRT {
  return "precio" in p;
}

/**
 * Arma 2-3 frases en español explicando la señal de un ticker a partir de
 * sus indicadores: RSI, MACD, Bollinger y volumen relativo.
 */
export function justificacionActivo(p: PrecioRT | RangoTicker, ticker: string): string {
  const frases: string[] = [];

  // ── RSI + MACD en una sola frase ───────────────────────────
  const rsi = p.rsi ?? 0;
  const zona = zonaRSI(rsi);
  const impulso = p.hist_subiendo
    ? "con impulso alcista según el MACD"
    : "sin impulso alcista todavía según el MACD";
  frases.push(`${ticker} tiene un RSI de ${rsi.toFixed(1)} (${zona}), ${impulso}.`);

  // ── Bollinger — solo si hay precio en vivo para comparar ───
  if (esPrecioRT(p)) {
    const precio = p.precio;
    const bandaInf = p.banda_inf;
    if (precio != null && bandaInf) {
      if (precio <= bandaInf) {
        frases.push(`El precio actual ($${precio.toFixed(2)}) está en o por debajo de la banda inferior de Bollinger ($${bandaInf.toFixed(2)}), lo que sugiere una posible zona de entrada.`);
      } else {
        frases.push(`El precio actual ($${precio.toFixed(2)}) está por encima de la banda inferior de Bollinger ($${bandaInf.toFixed(2)}).`);
      }
    }
  } else if (p.rango_entrar != null) {
    // Mercado cerrado: no hay precio en vivo, describir el rango calculado.
    frases.push(`El rango calculado para entrar hoy arranca en $${p.rango_entrar.toFixed(2)} (banda inferior de Bollinger).`);
  }

  // ── Volumen relativo ────────────────────────────────────────
  const volRatio = p.vol_ratio;
  if (volRatio != null) {
    frases.push(
      Math.abs(volRatio - 1) < 0.15
        ? "Volumen normal respecto al promedio de 20 días."
        : `Volumen ${volRatio.toFixed(1)}x el promedio de 20 días.`
    );
  }

  return frases.join(" ");
}

/**
 * Arma una frase agregada sobre el estado del portafolio: cuántos activos
 * están en señal de ENTRAR y cuántos en VIGILAR.
 */
export function resumenPortafolio(precios: Record<string, PrecioRT>): string {
  const tickers = Object.keys(precios);
  if (tickers.length === 0) return "";

  const entrar: string[] = [];
  let vigilar = 0;

  for (const ticker of tickers) {
    const senal = precios[ticker].senal;
    if (senal === "ENTRAR") entrar.push(ticker);
    else if (senal === "VIGILAR") vigilar += 1;
  }

  if (entrar.length === 0 && vigilar === 0) {
    return "Sin señales relevantes en este momento — todo el portafolio en zona neutral.";
  }

  const partes: string[] = [];
  if (entrar.length > 0) {
    partes.push(`${entrar.length} ${entrar.length === 1 ? "activo" : "activos"} en señal de entrada: ${entrar.join(", ")}.`);
  }
  if (vigilar > 0) {
    partes.push(`${vigilar} en vigilancia.`);
  }
  return partes.join(" ");
}
