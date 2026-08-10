export type Divisa = "USD" | "EUR" | "COP";

const SIMBOLOS: Record<Divisa, string> = {
  USD: "US$",
  EUR: "€",
  COP: "$",
};

interface Tasas {
  trm: number;       // COP por 1 USD
  tasa_eur: number;  // EUR por 1 USD
}

/**
 * Convierte un monto en USD (base nativa) a la divisa elegida y lo formatea.
 * USD → COP: ×TRM. USD → EUR: ×tasa_eur. USD se queda igual.
 */
export function mostrarMonto(montoUSD: number, divisa: Divisa, tasas: Tasas): string {
  const simbolo = SIMBOLOS[divisa];
  let valor = montoUSD;

  if (divisa === "COP") {
    valor = montoUSD * tasas.trm;
  } else if (divisa === "EUR") {
    valor = montoUSD * tasas.tasa_eur;
  }
  // USD se queda igual

  // USD/EUR con 2 decimales, COP sin decimales
  const decimales = divisa === "COP" ? 0 : 2;
  const formateado = valor.toLocaleString("es-CO", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });

  return `${simbolo}${formateado}`;
}